"""Store a calculated judge verdict for a prompt."""

from alembic import op
from sqlalchemy import inspect

revision = "002_judge_verdicts"
down_revision = "001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if "judge_verdicts" in inspect(bind).get_table_names():
        return
    from app.infrastructure.sqlite.orm import JudgeVerdictRow

    JudgeVerdictRow.__table__.create(bind=bind)


def downgrade() -> None:
    bind = op.get_bind()
    if "judge_verdicts" not in inspect(bind).get_table_names():
        return
    from app.infrastructure.sqlite.orm import JudgeVerdictRow

    JudgeVerdictRow.__table__.drop(bind=bind)
