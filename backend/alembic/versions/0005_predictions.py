"""Immutable prospective forecasts and separately settled outcomes."""
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from alembic import op

revision = "0005"
down_revision = "0004"


def upgrade():
    op.create_table(
        "prediction_models",
        sa.Column("version", sa.String, primary_key=True),
        sa.Column("bundle_sha256", sa.String, nullable=False),
        sa.Column("registered_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.clock_timestamp()),
        sa.Column("metadata", postgresql.JSONB, nullable=False),
    )
    op.create_table(
        "match_predictions",
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("match_id", sa.Integer, sa.ForeignKey("matches.id"), nullable=False),
        sa.Column("model_version", sa.String, sa.ForeignKey("prediction_models.version"), nullable=False),
        sa.Column("horizon_hours", sa.Integer, nullable=False),
        sa.Column("scheduled_kickoff", sa.DateTime(timezone=True), nullable=False),
        sa.Column("home_team_id", sa.Integer, nullable=False),
        sa.Column("away_team_id", sa.Integer, nullable=False),
        sa.Column("league", sa.String, nullable=False),
        sa.Column("feature_cutoff", sa.DateTime(timezone=True), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.clock_timestamp()),
        sa.Column("p_home", sa.Double, nullable=False),
        sa.Column("p_draw", sa.Double, nullable=False),
        sa.Column("p_away", sa.Double, nullable=False),
        sa.Column("features", postgresql.JSONB, nullable=False),
        sa.Column("provenance", postgresql.JSONB, nullable=False),
        sa.Column("baselines", postgresql.JSONB, nullable=False),
        sa.UniqueConstraint("match_id", "model_version", "horizon_hours", "scheduled_kickoff", name="uq_prediction_once"),
        sa.CheckConstraint("horizon_hours = 24", name="ck_prediction_horizon"),
        sa.CheckConstraint("p_home BETWEEN 0 AND 1 AND p_draw BETWEEN 0 AND 1 AND p_away BETWEEN 0 AND 1 "
                           "AND abs(p_home+p_draw+p_away-1) < 0.00000001", name="ck_prediction_probabilities"),
        sa.CheckConstraint("feature_cutoff <= generated_at AND generated_at < scheduled_kickoff", name="ck_prediction_before_game"),
    )
    op.create_index("ix_predictions_model_generated", "match_predictions", ["model_version", "generated_at"])
    op.create_index("ix_predictions_generated", "match_predictions", ["generated_at"])
    op.create_table(
        "prediction_results",
        sa.Column("prediction_id", sa.BigInteger, sa.ForeignKey("match_predictions.id"), primary_key=True),
        sa.Column("settled_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.clock_timestamp()),
        sa.Column("kind", sa.String, nullable=False),
        sa.Column("reason", sa.String),
        sa.Column("home_score", sa.Integer),
        sa.Column("away_score", sa.Integer),
        sa.Column("actual_kickoff", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("(kind = 'finished' AND reason IS NULL AND home_score >= 0 AND away_score >= 0) "
                           "OR (kind = 'void' AND reason IS NOT NULL AND home_score IS NULL AND away_score IS NULL)",
                           name="ck_prediction_settlement"),
    )
    # Preserve forecasts even if application code accidentally attempts an upsert,
    # DELETE or TRUNCATE. Trusted migrations can still deliberately change schema.
    op.execute("""
        CREATE FUNCTION public.predictions_immutable() RETURNS trigger
        LANGUAGE plpgsql AS $$ BEGIN
            RAISE EXCEPTION 'prediction history is append-only' USING ERRCODE = '23514';
        END $$
    """)
    for table in ("prediction_models", "match_predictions", "prediction_results"):
        op.execute(f"CREATE TRIGGER immutable_history BEFORE UPDATE OR DELETE OR TRUNCATE ON public.{table} "
                   "FOR EACH STATEMENT EXECUTE FUNCTION public.predictions_immutable()")
    op.execute("""
        CREATE FUNCTION public.validate_new_prediction() RETURNS trigger
        LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, public, pg_temp
        AS $$ DECLARE m public.matches%ROWTYPE; BEGIN
            NEW.generated_at := clock_timestamp();
            SELECT * INTO STRICT m FROM public.matches WHERE id = NEW.match_id FOR SHARE;
            IF m.status <> 'NS' OR m.kickoff <> NEW.scheduled_kickoff
               OR m.home_team_id <> NEW.home_team_id OR m.away_team_id <> NEW.away_team_id
               OR m.kickoff <= NEW.generated_at THEN
                RAISE EXCEPTION 'match changed or already started' USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
        END $$
    """)
    op.execute("CREATE TRIGGER validate_prediction BEFORE INSERT ON public.match_predictions "
               "FOR EACH ROW EXECUTE FUNCTION public.validate_new_prediction()")
    op.execute("""
        CREATE FUNCTION public.settle_new_prediction() RETURNS trigger
        LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, public, pg_temp
        AS $$ DECLARE p public.match_predictions%ROWTYPE; m public.matches%ROWTYPE; BEGIN
            SELECT * INTO STRICT p FROM public.match_predictions WHERE id = NEW.prediction_id;
            SELECT * INTO STRICT m FROM public.matches WHERE id = p.match_id FOR SHARE;
            NEW.settled_at := clock_timestamp(); NEW.actual_kickoff := m.kickoff;
            NEW.home_score := NULL; NEW.away_score := NULL; NEW.reason := NULL;
            IF m.kickoff <> p.scheduled_kickoff OR m.home_team_id <> p.home_team_id
               OR m.away_team_id <> p.away_team_id THEN
                NEW.kind := 'void'; NEW.reason := 'schedule_or_teams_changed';
            ELSIF m.status = 'CANC' THEN
                NEW.kind := 'void'; NEW.reason := 'cancelled';
            ELSIF m.status = 'FT' AND m.home_score IS NOT NULL AND m.away_score IS NOT NULL
                  AND m.home_score >= 0 AND m.away_score >= 0
                  AND m.kickoff + interval '3 hours' < NEW.settled_at THEN
                NEW.kind := 'finished'; NEW.home_score := m.home_score; NEW.away_score := m.away_score;
            ELSE
                RAISE EXCEPTION 'match result not ready' USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
        END $$
    """)
    op.execute("CREATE TRIGGER settle_prediction BEFORE INSERT ON public.prediction_results "
               "FOR EACH ROW EXECUTE FUNCTION public.settle_new_prediction()")
    for function in ("validate_new_prediction", "settle_new_prediction", "predictions_immutable"):
        op.execute(f"REVOKE ALL ON FUNCTION public.{function}() FROM PUBLIC")
    # Provisioning runs before migrations. The role may be absent in a test DB.
    op.execute("""
        DO $$ BEGIN
            IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'kickpick_predictor') THEN
                GRANT SELECT, INSERT ON prediction_models, match_predictions, prediction_results TO kickpick_predictor;
                GRANT USAGE, SELECT ON SEQUENCE match_predictions_id_seq TO kickpick_predictor;
            END IF;
            IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'kickpick_collector') THEN
                REVOKE INSERT, UPDATE, DELETE ON prediction_models, match_predictions, prediction_results FROM kickpick_collector;
            END IF;
        END $$
    """)


def downgrade():
    for table in ("prediction_results", "match_predictions", "prediction_models"):
        op.drop_table(table)
    for function in ("settle_new_prediction", "validate_new_prediction", "predictions_immutable"):
        op.execute(f"DROP FUNCTION public.{function}()")
