# Archetypes - Shared Agent Tools & Utilities

Reusable tool packages organized by domain. Framework-agnostic tools that work
with any agent framework (LangGraph, ADK, etc.).

## Installation

```bash
uv pip install -e examples/archetypes
```

## Domains

| Module | Description |
|--------|-------------|
| `archetypes.finance` | Portfolio, trading, market data tools |
| `archetypes.payments` | Customer profiles, transactions, refunds |
| `archetypes.communications` | Email, notifications, messaging |
| `archetypes.healthcare` | Clinical trials, EHR, patient data |

## Usage

```python
# Import specific tools
from archetypes.finance import get_portfolio, get_stock_quote
from archetypes.payments import get_customer_profile, initiate_refund
from archetypes.communications import send_email
from archetypes.healthcare import create_sample_patients, rule_based_assessment

# Or import entire domain
from archetypes import finance, payments
```

## Design Principles

1. **Framework Agnostic**: Plain Python functions compatible with any agent framework
2. **Typed Returns**: Pydantic models for structured, validated responses
3. **Mock Data**: Realistic mock data for demos and testing
4. **Rich Documentation**: Docstrings with demo IDs and example usage
