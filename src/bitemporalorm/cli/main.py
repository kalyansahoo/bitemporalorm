from __future__ import annotations

import importlib
import os
import sys

import typer
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax

app    = typer.Typer(name="bitemporalorm", add_completion=False)
console = Console()


def _load_models(models_module: str) -> None:
    """Import the user's models module so entities register themselves."""
    if models_module:
        sys.path.insert(0, os.getcwd())
        importlib.import_module(models_module)


@app.command()
def make_migration(
    name: str = typer.Argument("auto", help="Migration name (snake_case)"),
    migrations_dir: str = typer.Option("migrations", "--migrations-dir", "-d"),
    models_module: str = typer.Option("models", "--models", "-m",
                                       help="Python module path to import (e.g. 'myapp.models')"),
) -> None:
    """Generate a new migration file by diffing the current model state."""
    from bitemporalorm.migration.differ import SchemaDiffer, MigrationError
    from bitemporalorm.migration.loader import MigrationLoader
    from bitemporalorm.migration.state import MigrationState
    from bitemporalorm.migration.writer import MigrationWriter

    _load_models(models_module)

    # Current state from registry
    new_state = MigrationState.from_registry()

    # Previous state from existing migrations
    old_state = MigrationState.from_migration_history(migrations_dir)

    try:
        ops = SchemaDiffer().diff(old_state, new_state)
    except MigrationError as e:
        console.print(f"[red]Migration error:[/red] {e}")
        raise typer.Exit(1)

    if not ops:
        console.print("[green]No changes detected — migration not created.[/green]")
        return

    # Determine dependencies
    loader = MigrationLoader(migrations_dir)
    existing = loader.load()
    dependencies = [existing[-1].name] if existing else []

    # Auto-name from operations
    if name == "auto":
        op_name = ops[0].describe().lower()
        import re
        name = re.sub(r"[^a-z0-9]+", "_", op_name)[:40].strip("_") or "migration"

    writer = MigrationWriter(migrations_dir)
    filepath = writer.write(name, ops, dependencies)

    console.print(f"[green]Created[/green] {filepath}")
    for op in ops:
        console.print(f"  • {op.describe()}")


@app.command()
def migrate(
    migrations_dir: str = typer.Option("migrations", "--migrations-dir", "-d"),
    models_module: str  = typer.Option("models", "--models", "-m"),
    plan: bool          = typer.Option(False, "--plan", help="Print SQL without executing"),
    fake: bool          = typer.Option(False, "--fake", help="Mark as applied without running SQL"),
    db_url: str         = typer.Option("", "--db-url", envvar="DATABASE_URL",
                                        help="PostgreSQL DSN (or set DATABASE_URL env var)"),
) -> None:
    """Apply pending migrations to the database."""
    from bitemporalorm.connection.config import ConnectionConfig
    from bitemporalorm.migration.runner import MigrationRunner

    _load_models(models_module)

    config = _parse_db_url(db_url)
    runner = MigrationRunner(config)
    runner.ensure_migration_table()

    pending = runner.pending_migrations(migrations_dir)

    if not pending:
        console.print("[green]No pending migrations.[/green]")
        return

    if plan:
        sql_plan = runner.plan_sql(pending)
        console.print(Panel(Syntax(sql_plan, "sql", theme="monokai"), title="Migration Plan"))
        return

    for mig in pending:
        action = "Faking" if fake else "Applying"
        console.print(f"{action} [cyan]{mig.name}[/cyan] ...", end=" ")
        try:
            runner.apply(mig, fake=fake)
            console.print("[green]OK[/green]")
        except Exception as e:
            console.print(f"[red]FAILED[/red]\n{e}")
            raise typer.Exit(1)


def _parse_db_url(db_url: str) -> ConnectionConfig:
    """Parse a PostgreSQL DSN into ConnectionConfig."""
    from urllib.parse import urlparse

    if not db_url:
        db_url = os.environ.get("DATABASE_URL", "")
    if not db_url:
        raise typer.BadParameter(
            "Database URL is required. Pass --db-url or set the DATABASE_URL environment variable."
        )

    parsed = urlparse(db_url)
    return ConnectionConfig(
        host=parsed.hostname or "localhost",
        port=parsed.port or 5432,
        database=(parsed.path or "/").lstrip("/"),
        user=parsed.username or "postgres",
        password=parsed.password or "",
    )
