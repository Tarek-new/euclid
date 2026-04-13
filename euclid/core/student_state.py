from __future__ import annotations

import json
from datetime import datetime
from enum import Enum
from pathlib import Path

from sqlalchemy import DateTime, ForeignKey, String, Text, create_engine, func
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship


EUCLID_DIR = Path.home() / ".euclid"
EUCLID_DIR.mkdir(exist_ok=True)
DB_PATH = EUCLID_DIR / "state.db"


class ConceptState(str, Enum):
    UNKNOWN   = "unknown"
    SEEN      = "seen"
    LEARNING  = "learning"
    MASTERED  = "mastered"


class Base(DeclarativeBase):
    pass


class Student(Base):
    __tablename__ = "students"

    id:         Mapped[int]      = mapped_column(primary_key=True)
    name:       Mapped[str]      = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    last_seen:  Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now())

    concepts:  Mapped[list[ConceptRecord]] = relationship(back_populates="student", cascade="all, delete-orphan")
    sessions:  Mapped[list[SessionRecord]] = relationship(back_populates="student", cascade="all, delete-orphan")


class ConceptRecord(Base):
    __tablename__ = "concept_records"

    id:         Mapped[int]          = mapped_column(primary_key=True)
    student_id: Mapped[int]          = mapped_column(ForeignKey("students.id"))
    concept_id: Mapped[str]          = mapped_column(String(128))
    state:      Mapped[ConceptState] = mapped_column(String(32), default=ConceptState.UNKNOWN)
    attempts:   Mapped[int]          = mapped_column(default=0)
    correct:    Mapped[int]          = mapped_column(default=0)
    updated_at: Mapped[datetime]     = mapped_column(DateTime, default=func.now(), onupdate=func.now())

    student: Mapped[Student] = relationship(back_populates="concepts")


class SessionRecord(Base):
    __tablename__ = "sessions"

    id:           Mapped[int]      = mapped_column(primary_key=True)
    student_id:   Mapped[int]      = mapped_column(ForeignKey("students.id"))
    started_at:   Mapped[datetime] = mapped_column(DateTime, default=func.now())
    ended_at:     Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    concepts_hit: Mapped[str]      = mapped_column(Text, default="[]")
    summary:      Mapped[str]      = mapped_column(Text, default="")

    student: Mapped[Student] = relationship(back_populates="sessions")

    def add_concept(self, concept_id: str) -> None:
        hits = json.loads(self.concepts_hit)
        if concept_id not in hits:
            hits.append(concept_id)
        self.concepts_hit = json.dumps(hits)


engine = create_engine(f"sqlite:///{DB_PATH}", echo=False)
Base.metadata.create_all(engine)


class StateManager:
    def __init__(self, student_name: str = "default") -> None:
        self.student_name = student_name
        self._session: Session = Session(engine)
        self.student   = self._get_or_create_student()
        self.current_session = self._start_session()

    def _get_or_create_student(self) -> Student:
        student = self._session.query(Student).filter_by(name=self.student_name).first()
        if not student:
            student = Student(name=self.student_name)
            self._session.add(student)
            self._session.commit()
        return student

    def _start_session(self) -> SessionRecord:
        record = SessionRecord(student_id=self.student.id)
        self._session.add(record)
        self._session.commit()
        return record

    def get_concept_state(self, concept_id: str) -> ConceptState:
        record = self._session.query(ConceptRecord).filter_by(
            student_id=self.student.id, concept_id=concept_id
        ).first()
        return record.state if record else ConceptState.UNKNOWN

    def set_concept_state(self, concept_id: str, state: ConceptState) -> None:
        record = self._session.query(ConceptRecord).filter_by(
            student_id=self.student.id, concept_id=concept_id
        ).first()
        if not record:
            record = ConceptRecord(student_id=self.student.id, concept_id=concept_id)
            self._session.add(record)
        record.state = state
        self.current_session.add_concept(concept_id)
        self._session.commit()

    def record_attempt(self, concept_id: str, correct: bool) -> None:
        record = self._session.query(ConceptRecord).filter_by(
            student_id=self.student.id, concept_id=concept_id
        ).first()
        if not record:
            record = ConceptRecord(
                student_id=self.student.id, 
                concept_id=concept_id,
                attempts=0,  # Explicitly set to 0
                correct=0    # Explicitly set to 0
            )
            self._session.add(record)
        record.attempts += 1
        if correct:
            record.correct += 1
        self._session.commit()

    def get_all_states(self) -> dict[str, ConceptState]:
        records = self._session.query(ConceptRecord).filter_by(student_id=self.student.id).all()
        return {r.concept_id: r.state for r in records}

    def get_mastered(self) -> set[str]:
        return {
            r.concept_id
            for r in self._session.query(ConceptRecord).filter_by(
                student_id=self.student.id, state=ConceptState.MASTERED
            ).all()
        }

    def end_session(self, summary: str = "") -> None:
        self.current_session.ended_at = datetime.now()
        self.current_session.summary  = summary
        self._session.commit()
        self._session.close()
