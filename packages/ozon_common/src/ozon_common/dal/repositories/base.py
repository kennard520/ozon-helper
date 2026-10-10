from __future__ import annotations

from sqlalchemy.orm import Session

from ozon_common.dal.session import current_session


class BaseRepo:
    @property
    def s(self) -> Session:
        return current_session()
