"""SQLite schema migrations for TSF state."""

from __future__ import annotations

import sqlite3


SCHEMA_VERSION = 1


def initialize_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        PRAGMA foreign_keys = ON;
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version INTEGER PRIMARY KEY,
            applied_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS tasks (
            task_id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            objective TEXT NOT NULL,
            assigned_agent_id TEXT,
            created_by_agent_id TEXT NOT NULL,
            risk_level TEXT NOT NULL,
            status TEXT NOT NULL,
            external_effect INTEGER NOT NULL,
            budget_limit REAL,
            max_steps INTEGER,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            plain_english_summary TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS task_events (
            event_id TEXT PRIMARY KEY,
            task_id TEXT NOT NULL,
            created_at TEXT NOT NULL,
            summary TEXT NOT NULL,
            metadata_json TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS messages (
            message_id TEXT PRIMARY KEY,
            sender_agent_id TEXT NOT NULL,
            recipient_agent_id TEXT,
            channel TEXT,
            task_id TEXT,
            message_type TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS approval_requests (
            approval_id TEXT PRIMARY KEY,
            task_id TEXT NOT NULL,
            agent_id TEXT NOT NULL,
            requested_action TEXT NOT NULL,
            risk_level TEXT NOT NULL,
            external_effect INTEGER NOT NULL,
            plain_english_request TEXT NOT NULL,
            guardian_review TEXT,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL,
            decided_at TEXT
        );
        CREATE TABLE IF NOT EXISTS approval_decisions (
            decision_id TEXT PRIMARY KEY,
            approval_id TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            signature TEXT,
            dry_run INTEGER NOT NULL,
            executable INTEGER NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS budget_usage (
            usage_id TEXT PRIMARY KEY,
            agent_id TEXT,
            task_id TEXT,
            amount_usd REAL NOT NULL,
            loop_steps INTEGER NOT NULL,
            tool_calls INTEGER NOT NULL,
            summary TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS audit_log (
            audit_id TEXT PRIMARY KEY,
            sequence_number INTEGER NOT NULL UNIQUE,
            created_at TEXT NOT NULL,
            actor_type TEXT NOT NULL,
            actor_id TEXT NOT NULL,
            action TEXT NOT NULL,
            target_type TEXT NOT NULL,
            target_id TEXT NOT NULL,
            risk_level TEXT NOT NULL,
            external_effect INTEGER NOT NULL,
            summary TEXT NOT NULL,
            metadata_json TEXT NOT NULL,
            previous_hash TEXT NOT NULL,
            entry_hash TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS worker_proposals (
            proposal_id TEXT PRIMARY KEY,
            payload_json TEXT NOT NULL,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS self_improvement_proposals (
            proposal_id TEXT PRIMARY KEY,
            payload_json TEXT NOT NULL,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS daily_reports (
            report_id TEXT PRIMARY KEY,
            report_date TEXT NOT NULL,
            content TEXT NOT NULL,
            telegram_summary TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS runtime_status (
            singleton_id INTEGER PRIMARY KEY CHECK (singleton_id = 1),
            status TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS execution_queue (
            queue_id TEXT PRIMARY KEY,
            task_id TEXT NOT NULL,
            agent_id TEXT NOT NULL,
            action TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            external_effect INTEGER NOT NULL,
            approval_id TEXT,
            approval_decision_id TEXT,
            action_hash TEXT NOT NULL,
            status TEXT NOT NULL,
            result_summary TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS notification_queue (
            notification_id TEXT PRIMARY KEY,
            notification_type TEXT NOT NULL,
            chat_id TEXT,
            body TEXT NOT NULL,
            status TEXT NOT NULL,
            dry_run INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            sent_at TEXT
        );
        CREATE TABLE IF NOT EXISTS kill_confirmations (
            confirmation_id TEXT PRIMARY KEY,
            chat_id TEXT NOT NULL,
            code TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            used INTEGER NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS provider_auth_sessions (
            session_id TEXT PRIMARY KEY,
            provider TEXT NOT NULL,
            auth_method TEXT NOT NULL,
            requested_by TEXT NOT NULL,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            expires_at TEXT,
            login_url_present INTEGER NOT NULL,
            device_code_present INTEGER NOT NULL,
            account_label TEXT,
            model_route TEXT NOT NULL,
            credential_storage TEXT NOT NULL,
            safe_summary TEXT NOT NULL,
            last_error_redacted TEXT
        );
        CREATE TABLE IF NOT EXISTS human_tasks (
            human_task_id TEXT PRIMARY KEY,
            requested_by_agent_id TEXT NOT NULL,
            related_task_id TEXT,
            title TEXT NOT NULL,
            plain_english_request TEXT NOT NULL,
            reason TEXT NOT NULL,
            priority TEXT NOT NULL,
            deadline TEXT,
            cost_estimate TEXT,
            risk_level TEXT NOT NULL,
            public_summary TEXT NOT NULL,
            private_details_redacted TEXT,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            completed_at TEXT,
            founder_note TEXT
        );
        CREATE TABLE IF NOT EXISTS workdays (
            workday_id TEXT PRIMARY KEY,
            workday_date TEXT NOT NULL,
            timezone TEXT NOT NULL,
            status TEXT NOT NULL,
            started_at TEXT,
            closed_at TEXT,
            atlas_plan_id TEXT,
            public_report_id TEXT,
            private_report_id TEXT,
            cycle_count INTEGER NOT NULL,
            last_cycle_at TEXT,
            summary TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS daily_plans (
            plan_id TEXT PRIMARY KEY,
            workday_id TEXT NOT NULL,
            created_by_agent_id TEXT NOT NULL,
            objective TEXT NOT NULL,
            priorities_json TEXT NOT NULL,
            agent_assignments_json TEXT NOT NULL,
            constraints_json TEXT NOT NULL,
            real_data_sources_used_json TEXT NOT NULL,
            assumptions_json TEXT NOT NULL,
            open_questions_json TEXT NOT NULL,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS founder_messages (
            message_id TEXT PRIMARY KEY,
            source TEXT NOT NULL,
            received_at TEXT NOT NULL,
            sender TEXT NOT NULL,
            target_agent TEXT NOT NULL,
            priority TEXT NOT NULL,
            message_type TEXT NOT NULL,
            content TEXT NOT NULL,
            status TEXT NOT NULL,
            reviewed_by_agent_id TEXT,
            reviewed_at TEXT,
            related_human_task_id TEXT,
            related_task_id TEXT
        );
        CREATE TABLE IF NOT EXISTS scheduler_runs (
            scheduler_run_id TEXT PRIMARY KEY,
            started_at TEXT NOT NULL,
            ended_at TEXT,
            mode TEXT NOT NULL,
            status TEXT NOT NULL,
            checkpoint_type TEXT NOT NULL,
            workday_id TEXT,
            cycle_id TEXT,
            lock_id TEXT,
            summary TEXT NOT NULL,
            error_redacted TEXT
        );
        CREATE TABLE IF NOT EXISTS scheduler_locks (
            lock_id TEXT PRIMARY KEY,
            acquired_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            owner TEXT NOT NULL,
            status TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS deployment_records (
            deployment_id TEXT PRIMARY KEY,
            target TEXT NOT NULL,
            environment TEXT NOT NULL,
            state TEXT NOT NULL,
            plan_json TEXT NOT NULL,
            checks_json TEXT NOT NULL,
            health_check_json TEXT NOT NULL,
            rollback_plan_json TEXT NOT NULL,
            preview_url TEXT,
            public_summary TEXT NOT NULL,
            blocked_reason TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS deployment_credential_status (
            check_id TEXT PRIMARY KEY,
            provider TEXT NOT NULL,
            enabled INTEGER NOT NULL,
            cli_available INTEGER NOT NULL,
            cli_version_redacted TEXT,
            credential_present INTEGER NOT NULL,
            credential_source TEXT NOT NULL,
            project_linked INTEGER NOT NULL,
            target_configured INTEGER NOT NULL,
            safe_summary TEXT NOT NULL,
            missing_requirements_json TEXT NOT NULL,
            human_task_required INTEGER NOT NULL,
            checked_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS cost_items (
            cost_item_id TEXT PRIMARY KEY,
            month TEXT NOT NULL,
            category TEXT NOT NULL,
            provider TEXT NOT NULL,
            service_name TEXT NOT NULL,
            description TEXT NOT NULL,
            amount_eur REAL,
            amount_original REAL,
            currency_original TEXT NOT NULL,
            is_recurring INTEGER NOT NULL,
            recurrence TEXT NOT NULL,
            confidence TEXT NOT NULL,
            source TEXT NOT NULL,
            public_summary TEXT NOT NULL,
            private_notes_redacted TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS cost_decisions (
            decision_id TEXT PRIMARY KEY,
            action_name TEXT NOT NULL,
            allowed INTEGER NOT NULL,
            status TEXT NOT NULL,
            reason TEXT NOT NULL,
            known_monthly_burn_eur REAL NOT NULL,
            projected_monthly_burn_eur REAL,
            unknown_cost_count INTEGER NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS telegram_poll_state (
            state_key TEXT PRIMARY KEY,
            state_value TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS code_change_proposals (
            proposal_id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            summary TEXT NOT NULL,
            rationale TEXT NOT NULL,
            patch_text TEXT NOT NULL,
            target_branch TEXT NOT NULL,
            base_branch TEXT NOT NULL,
            status TEXT NOT NULL,
            created_by_agent_id TEXT NOT NULL,
            reviewed_by_atlas INTEGER NOT NULL,
            reviewed_by_sentinel INTEGER NOT NULL,
            tests_command TEXT NOT NULL,
            test_status TEXT,
            test_summary TEXT,
            commit_sha TEXT,
            pushed_branch TEXT,
            public_summary TEXT NOT NULL,
            private_notes_redacted TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            applied_at TEXT
        );
        """
    )
    connection.commit()
