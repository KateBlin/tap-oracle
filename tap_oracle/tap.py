from __future__ import annotations

from singer_sdk import SQLTap, typing as th
from tap_oracle.client import OracleConnector, OracleStream


class TapOracle(SQLTap):
    """Oracle Singer tap built with the Meltano SDK."""

    name = "tap-oracle"
    default_stream_class = OracleStream

    config_jsonschema = th.PropertiesList(
        # --- Connection ---
        th.Property("host",         th.StringType,  required=True,
                    description="Oracle server hostname or IP"),
        th.Property("port",         th.IntegerType, default=1521,
                    description="Oracle listener port"),
        th.Property("user",         th.StringType,  required=True,
                    description="Oracle username"),
        th.Property("password",     th.StringType,  required=True, secret=True,
                    description="Oracle password"),
        th.Property("service_name", th.StringType,
                    description="Oracle service name (preferred over SID)"),
        th.Property("sid",          th.StringType,
                    description="Oracle SID (legacy, use service_name instead)"),

        # --- Driver options ---
        th.Property("thick_mode",   th.BooleanType, default=False,
                    description="Use thick mode (requires Oracle Client installed)"),
        th.Property("https_proxy",  th.StringType,
                    description="HTTPS proxy URL for thin mode connections"),

        # --- Performance ---
        th.Property("cursor_array_size", th.IntegerType, default=1000,
                    description="Rows fetched per round-trip (arraysize). "
                                "Increase to 10000+ for fast networks."),

        # --- Discovery filtering ---
        th.Property("filter_schemas", th.StringType,
                    description="Comma-separated schema names to discover. "
                                "Speeds up discovery on large databases."),
        th.Property("filter_tables",
                    th.ArrayType(th.StringType),
                    description='Tables to include, format: ["SCHEMA-TABLE", ...]. '
                                'Matches the pipelinewise-tap-oracle convention.'),
        th.Property(
            "stream_options",
            th.ObjectType(
                additional_properties=th.ObjectType(
                    th.Property(
                        "custom_where_clauses",
                        th.ArrayType(th.StringType),
                        default=[],
                        description=(
                            "If an array of custom WHERE clauses is provided, the tap "
                            "will only process the records that match the WHERE "
                            "clauses. "
                            "The WHERE clauses are combined using the AND operator."
                        ),
                    ),
                ),
            ),
        ),
        # --- Replication ---
        th.Property("start_date",   th.DateTimeType,
                    description="Earliest date for incremental replication"),
    ).to_dict()


if __name__ == "__main__":
    TapOracle.cli()
