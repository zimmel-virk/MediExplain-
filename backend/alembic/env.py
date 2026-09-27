from logging.config import fileConfig
from alembic import context
from sqlalchemy import engine_from_config, pool

from app.core.config import settings
from app.core.base import Base
import app.models

# Alembic uses this configuration object to read the migration settings.
config = context.config

# Load the logging configuration when an Alembic config file is available.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Alembic runs migrations synchronously, so the async SQLite driver is
# converted to the standard SQLite connection format for migration commands.
sync_url = settings.DATABASE_URL.replace("sqlite+aiosqlite", "sqlite")
config.set_main_option("sqlalchemy.url", sync_url)

# Base metadata gives Alembic access to the application's database models.
target_metadata = Base.metadata


# Offline migrations generate SQL without creating a live database connection.
def run_migrations_offline():
    context.configure(
        url=sync_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
        compare_type=False,
    )

    # Run the migration inside Alembic's transaction context.
    with context.begin_transaction():
        context.run_migrations()


# Online migrations connect directly to the configured database.
def run_migrations_online():
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    # The active connection is passed to Alembic so migrations can be
    # applied directly to the database.
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,
            compare_type=False,
        )

        with context.begin_transaction():
            context.run_migrations()


# Alembic selects the appropriate migration method depending on how it is run.
if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()