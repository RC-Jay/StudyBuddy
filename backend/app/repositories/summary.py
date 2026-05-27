import uuid

from fastapi import Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.summary import Summary


class SummaryRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def list_for_user(self, user_id: uuid.UUID) -> list[Summary]:
        return (
            self._db.query(Summary)
            .filter_by(user_id=user_id)
            .order_by(Summary.created_at.asc())
            .all()
        )

    def create(self, summary: Summary) -> Summary:
        self._db.add(summary)
        self._db.commit()
        self._db.refresh(summary)
        return summary


# FastAPI dependency
def get_summary_repo(db: Session = Depends(get_db)) -> SummaryRepository:
    return SummaryRepository(db)
