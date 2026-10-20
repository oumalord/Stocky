"""Permission codes and default roles. Roles are copied per organisation so each can customise its own."""

PERMISSIONS = {
    "product.view": "View products", "product.manage": "Create, edit and archive products",
    "location.view": "View branches and locations", "location.manage": "Manage branches and locations",
    "movement.view": "View the stock ledger and balances", "movement.post": "Post stock movements",
    "movement.reverse": "Reverse stock movements", "audit.view": "View the audit trail",
    "count.view": "View stock counts", "count.manage": "Create and submit stock counts",
    "variance.view": "View submitted stock variances",
    "team.manage": "Manage users and roles", "settings.manage": "Manage organisation settings",
}

_VIEW = ["product.view", "location.view", "movement.view"]

DEFAULT_ROLES = {
    "owner": {"name": "Organisation owner", "permissions": ["*"]},
    "admin": {"name": "Organisation administrator", "permissions": ["*"]},
    "inventory_manager": {"name": "Inventory manager", "permissions": _VIEW + [
        "product.manage", "location.manage", "movement.post", "movement.reverse", "count.view", "count.manage",
        "variance.view"]},
    "branch_manager": {"name": "Warehouse or branch manager", "permissions": _VIEW + [
        "movement.post", "count.view", "count.manage", "variance.view"]},
    "counter": {"name": "Stock counter", "permissions": ["product.view", "location.view", "count.view", "count.manage"]},
    "investigator": {"name": "Investigator", "permissions": _VIEW + ["count.view", "variance.view"]},
    "approver": {"name": "Approver or finance controller", "permissions": _VIEW + ["count.view", "variance.view"]},
    "auditor": {"name": "Auditor", "permissions": _VIEW + ["count.view", "variance.view", "audit.view"]},
    "executive": {"name": "Read-only executive", "permissions": _VIEW + ["count.view", "variance.view"]},
}
