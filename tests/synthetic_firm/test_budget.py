from synthetic_firm.budget import BudgetPolicy, BudgetUsage, evaluate_budget


def test_budget_enforcement_allows_within_limits():
    decision = evaluate_budget(
        BudgetPolicy(10.0, 5.0, 25.0, 10, 20),
        BudgetUsage(1.0, 1.0, 2.0, 3, 4),
    )

    assert decision.allowed is True


def test_budget_enforcement_blocks_exceeded_task_budget():
    decision = evaluate_budget(
        BudgetPolicy(10.0, 5.0, 25.0, 10, 20),
        BudgetUsage(1.0, 6.0, 2.0, 3, 4),
    )

    assert decision.allowed is False
    assert "task budget exceeded" in decision.reason


def test_budget_enforcement_fails_closed_when_unknown():
    decision = evaluate_budget(
        BudgetPolicy(10.0, 5.0, 25.0, 10, 20),
        BudgetUsage(None, 1.0, 2.0, 3, 4),
    )

    assert decision.allowed is False
    assert "failing closed" in decision.reason
