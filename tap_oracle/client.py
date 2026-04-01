from __future__ import annotations

import functools
from urllib.parse import quote_plus
from typing import Any

import sqlalchemy as sa
from singer_sdk import typing as th
from singer_sdk.sql import SQLConnector, SQLStream, SQLTap
from singer_sdk.sql.connector import SQLToJSONSchema

try:
    import oracledb
    from sqlalchemy.dialects.oracle import (
        CLOB, BLOB, NUMBER, DATE, TIMESTAMP,
        NCLOB, NVARCHAR2, VARCHAR2, CHAR, FLOAT,
        BINARY_FLOAT, BINARY_DOUBLE, RAW, LONG,
        INTERVAL,
    )
except ImportError:
    pass


class OracleTypeMapper(SQLToJSONSchema):
    """Map Oracle-specific column types to JSON Schema."""

    @functools.singledispatchmethod
    def to_jsonschema(self, column_type):
        return super().to_jsonschema(column_type)

    @to_jsonschema.register(NUMBER)
    def number_to_jsonschema(self, column_type: NUMBER):
        """Oracle NUMBER can be integer or decimal depending on scale."""
        if column_type.scale == 0 and column_type.precision:
            return th.IntegerType().to_dict()
        if column_type.scale and column_type.scale > 0:
            return {
                "type": ["number", "null"],
                "multipleOf": 10 ** -column_type.scale,
            }
        # Unknown precision/scale — emit as string to avoid precision loss
        return th.StringType().to_dict()

    @to_jsonschema.register(CLOB)
    @to_jsonschema.register(NCLOB)
    @to_jsonschema.register(LONG)
    def lob_to_jsonschema(self, column_type):
        return th.StringType().to_dict()

    @to_jsonschema.register(BLOB)
    @to_jsonschema.register(RAW)
    def binary_to_jsonschema(self, column_type):
        return {"type": ["string", "null"], "contentEncoding": "base64"}

    @to_jsonschema.register(BINARY_FLOAT)
    @to_jsonschema.register(BINARY_DOUBLE)
    @to_jsonschema.register(FLOAT)
    def float_to_jsonschema(self, column_type):
        return th.NumberType().to_dict()

    @to_jsonschema.register(DATE)
    @to_jsonschema.register(TIMESTAMP)
    def date_to_jsonschema(self, column_type):
        return th.DateTimeType().to_dict()


class OracleConnector(SQLConnector):
    """SQLAlchemy connector for Oracle using python-oracledb."""

    @property
    def sql_to_jsonschema(self) -> OracleTypeMapper:
        return OracleTypeMapper()

    def get_sqlalchemy_url(self, config: dict) -> str:
        """Build the Oracle SQLAlchemy connection URL."""
        host = config["host"]
        port = config.get("port", 1521)
        user = config["user"]
        password = config["password"]
        service_name = config.get("service_name")
        sid = config.get("sid")

        encoded_user = quote_plus(str(user))
        encoded_password = quote_plus(str(password))

        # In SQLAlchemy/oracledb, path-style DSN is interpreted as SID.
        # Use explicit query params so service_name is handled correctly.
        base = f"oracle+oracledb://{encoded_user}:{encoded_password}@{host}:{port}/"

        # Service name (preferred) or SID
        if service_name:
            return f"{base}?service_name={quote_plus(str(service_name))}"
        if sid:
            return f"{base}?sid={quote_plus(str(sid))}"

        raise ValueError("Either 'service_name' or 'sid' must be provided.")

    def create_engine(self) -> sa.engine.Engine:
        """Create the SQLAlchemy engine with Oracle-specific options."""
        url = self.get_sqlalchemy_url(self.config)

        connect_args: dict[str, Any] = {}

        # Thin mode: no Oracle Client required
        if self.config.get("thick_mode", False):
            oracledb.init_oracle_client()

        # Optional: HTTPS proxy for thin mode
        if proxy := self.config.get("https_proxy"):
            connect_args["https_proxy"] = proxy

        return sa.create_engine(
            url,
            arraysize=self.config.get("cursor_array_size", 1000),
            connect_args=connect_args,
            # Disable server-side cursors (not needed with arraysize)
            execution_options={"stream_results": False},
        )

    def get_schema_names(self, engine, inspected) -> list[str]:
        """Filter schemas if filter_schemas is set."""
        all_schemas = super().get_schema_names(engine, inspected)
        if schemas := self.config.get("filter_schemas"):
            # filter_schemas can be a string or list
            if isinstance(schemas, str):
                schemas = [s.strip() for s in schemas.split(",")]
            return [s for s in all_schemas if s.upper() in
                    [f.upper() for f in schemas]]
        return all_schemas

    def get_object_names(self, engine, inspected, schema_name):
        """Filter tables if filter_tables is set."""
        objects = super().get_object_names(engine, inspected, schema_name)
        if tables := self.config.get("filter_tables"):
            # filter_tables: ["SCHEMA-TABLE", ...] like the old tap
            allowed = {t.split("-")[1].upper() for t in tables
                       if "-" in t and t.split("-")[0].upper() == schema_name.upper()}
            if allowed:
                return [(name, is_view) for name, is_view in objects
                        if name.upper() in allowed]
        return objects


class OracleStream(SQLStream):
    """Stream class for Oracle tables."""

    connector_class = OracleConnector