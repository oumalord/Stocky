from django.apps import AppConfig
from django.db import connection
from django.db.models.signals import post_migrate

APPEND_ONLY_TABLES = ["audit_auditevent", "inventory_stockmovement"]

TRIGGER_SQL = """
CREATE OR REPLACE FUNCTION stockpilot_append_only() RETURNS trigger AS $$
BEGIN RAISE EXCEPTION '% is append-only', TG_TABLE_NAME; END; $$ LANGUAGE plpgsql;
DROP TRIGGER IF EXISTS append_only_guard ON {table};
CREATE TRIGGER append_only_guard BEFORE UPDATE OR DELETE ON {table}
FOR EACH ROW EXECUTE FUNCTION stockpilot_append_only();
"""


def install_append_only_triggers(sender, using="default", **kwargs):
    """DB-level backstop for the ORM-level immutability checks (PostgreSQL only)."""
    from django.db import connections

    conn = connections[using]
    if conn.vendor != "postgresql":
        return
    with conn.cursor() as cur:
        existing = set(conn.introspection.table_names(cur))
        for table in APPEND_ONLY_TABLES:
            if table in existing:
                cur.execute(TRIGGER_SQL.format(table=table))


class AuditConfig(AppConfig):
    name = "apps.audit"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self):
        post_migrate.connect(install_append_only_triggers, sender=self)
