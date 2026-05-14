import os
from pathlib import Path

from dotenv import dotenv_values, load_dotenv, find_dotenv
from testcontainers.postgres import PostgresContainer

MANDATORY_ENV_VARS = (
    "POSTGRES_VERSION",
    "PGMQ_VERSION",
    "DB_USER",
    "DB_PASS",
    "DB_NAME",
    "DB_HOST",
    "DB_PORT",
)

load_dotenv(find_dotenv())


def start_pgmq_container(
    postgres_version: str,
    pgmq_version: str,
    db_user: str,
    db_pass: str,
    db_name: str,
) -> PostgresContainer:
    container = PostgresContainer(
        image=f"ghcr.io/pgmq/pg{postgres_version}-pgmq:{pgmq_version}",
        username=db_user,
        password=db_pass,
        dbname=db_name,
    )
    container.start()
    os.environ["DB_HOST"] = container.get_container_host_ip()
    os.environ["DB_PORT"] = str(container.get_exposed_port(5432))
    return container


def bootstrap_postgres() -> PostgresContainer | None:
    _assert_test_database_environment()

    tc_value = os.getenv("TEST_CONTAINER")

    if tc_value is not None and tc_value.lower() in ("false", "0"):
        return None

    return start_pgmq_container(
        postgres_version=os.environ["POSTGRES_VERSION"],
        pgmq_version=os.environ["PGMQ_VERSION"],
        db_user=os.environ["DB_USER"],
        db_pass=os.environ["DB_PASS"],
        db_name=os.environ["DB_NAME"],
    )


def _assert_test_database_environment() -> None:
    test_env_path = Path(__file__).resolve().parent.parent / ".env.test"
    expected_db_name = dotenv_values(test_env_path).get("DB_NAME")
    actual_db_name = os.environ.get("DB_NAME")

    if not expected_db_name:
        raise RuntimeError(f"DB_NAME is missing in {test_env_path}")

    if actual_db_name != expected_db_name:
        raise RuntimeError(
            "Unsafe test database configuration: "
            f"expected DB_NAME={expected_db_name!r} from {test_env_path.name}, "
            f"got DB_NAME={actual_db_name!r}. "
            "Refusing to start tests to avoid touching a non-test database."
        )

    missing_env_vars = [
        env_var for env_var in MANDATORY_ENV_VARS if not (os.getenv(env_var))
    ]
    if missing_env_vars:
        raise RuntimeError(f"Missing environment variables: {missing_env_vars}")
