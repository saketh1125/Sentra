"""001 initial schema — 8 tables + pgvector 384

Revision ID: 001_initial_schema
Revises:
Create Date: 2026-10-24
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision: str = "001_initial_schema"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")

    op.create_table(
        "repositories",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("remote_url", sa.Text, nullable=False),
        sa.Column("branch", sa.Text, nullable=False, server_default="main"),
        sa.Column("commit_sha", sa.Text, nullable=True),
        sa.Column("status", sa.Text, nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )

    op.create_table(
        "files",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("repo_id", UUID(as_uuid=True), sa.ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False),
        sa.Column("path", sa.Text, nullable=False),
        sa.Column("language", sa.Text, nullable=True),
        sa.Column("byte_len", sa.Integer, nullable=True),
        sa.Column("content_hash", sa.Text, nullable=True),
    )
    op.create_index("ix_files_repo_id", "files", ["repo_id"])

    op.create_table(
        "chunks",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("file_id", UUID(as_uuid=True), sa.ForeignKey("files.id", ondelete="CASCADE"), nullable=False),
        sa.Column("repo_id", UUID(as_uuid=True), sa.ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.Text, nullable=False),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("qualified_name", sa.Text, nullable=False),
        sa.Column("start_line", sa.Integer, nullable=False),
        sa.Column("end_line", sa.Integer, nullable=False),
        sa.Column("byte_start", sa.Integer, nullable=False),
        sa.Column("byte_end", sa.Integer, nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("content_hash", sa.Text, nullable=False),
        sa.Column("parent_kind", sa.Text, nullable=True),
        sa.Column("line_count", sa.Integer, nullable=True),
        sa.Column("oversized", sa.Boolean, nullable=False, server_default="false"),
    )
    op.create_index("ix_chunks_file_id", "chunks", ["file_id"])
    op.create_index("ix_chunks_repo_id", "chunks", ["repo_id"])

    op.create_table(
        "embeddings",
        sa.Column("chunk_id", UUID(as_uuid=True), sa.ForeignKey("chunks.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("embedding", sa.Text, nullable=False),
        sa.Column("model", sa.Text, nullable=False, server_default="BAAI/bge-small-en-v1.5"),
        sa.Column("render_mode", sa.Text, nullable=True),
    )
    op.execute("ALTER TABLE embeddings ALTER COLUMN embedding TYPE vector(384) USING embedding::vector(384)")
    op.execute("CREATE INDEX ix_embeddings_hnsw ON embeddings USING hnsw (embedding vector_cosine_ops)")

    op.create_table(
        "documents",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("chunk_id", UUID(as_uuid=True), sa.ForeignKey("chunks.id", ondelete="CASCADE"), nullable=True),
        sa.Column("text", sa.Text, nullable=False),
        sa.Column("source_hash", sa.Text, nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("doc_embedding", sa.Text, nullable=True),
    )
    op.execute("ALTER TABLE documents ALTER COLUMN doc_embedding TYPE vector(384) USING doc_embedding::vector(384)")
    op.create_index("ix_documents_chunk_id", "documents", ["chunk_id"])

    op.create_table(
        "findings",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("repo_id", UUID(as_uuid=True), sa.ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False),
        sa.Column("module", sa.Text, nullable=False),
        sa.Column("severity", sa.Text, nullable=False),
        sa.Column("location", JSONB, nullable=True),
        sa.Column("source", sa.Text, nullable=True),
        sa.Column("explanation", sa.Text, nullable=True),
        sa.Column("status", sa.Text, nullable=False, server_default="open"),
        sa.Column("stable_key", sa.Text, unique=True, nullable=True),
        sa.Column("detail", JSONB, nullable=True),
        sa.Column("canonical_id", sa.Text, nullable=True),
    )
    op.create_index("ix_findings_repo_id", "findings", ["repo_id"])

    op.create_table(
        "pr_analyses",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("repo_id", UUID(as_uuid=True), sa.ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False),
        sa.Column("pr_number", sa.Integer, nullable=False),
        sa.Column("head_sha", sa.Text, nullable=True),
        sa.Column("findings", JSONB, nullable=True),
        sa.Column("summary", JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_pr_analyses_repo_id", "pr_analyses", ["repo_id"])

    op.create_table(
        "score_snapshots",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("repo_id", UUID(as_uuid=True), sa.ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False),
        sa.Column("score", sa.Integer, nullable=False),
        sa.Column("label", sa.Text, nullable=False),
        sa.Column("breakdown", JSONB, nullable=True),
        sa.Column("config_snapshot", JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_score_snapshots_repo_id", "score_snapshots", ["repo_id"])


def downgrade() -> None:
    op.drop_table("score_snapshots")
    op.drop_table("pr_analyses")
    op.drop_table("findings")
    op.drop_table("documents")
    op.drop_table("embeddings")
    op.drop_table("chunks")
    op.drop_table("files")
    op.drop_table("repositories")
