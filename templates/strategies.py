STRATEGY_TEMPLATES = [
    {
        "name": "Golden Cross (20/50)",
        "conditions": [
            {"indicator": "MA_CROSS_20_50", "operator": "CROSS_ABOVE", "value": 0},
            {"indicator": "VOLUME_SPIKE", "operator": ">", "value": 1.5},
        ],
        "market": "BOTH",
        "is_template": True,
    },
    {
        "name": "RSI Oversold Bounce",
        "conditions": [
            {"indicator": "RSI", "operator": "<", "value": 30},
            {"indicator": "PRICE_ABOVE_MA200", "operator": "==", "value": 1},
        ],
        "market": "BOTH",
        "is_template": True,
    },
    {
        "name": "Value + Momentum",
        "conditions": [
            {"indicator": "PER", "operator": "<", "value": 15},
            {"indicator": "RSI", "operator": ">", "value": 50},
            {"indicator": "PRICE_ABOVE_MA200", "operator": "==", "value": 1},
        ],
        "market": "BOTH",
        "is_template": True,
    },
    {
        "name": "Breakout Volume",
        "conditions": [
            {"indicator": "VOLUME_SPIKE", "operator": ">", "value": 2.0},
            {"indicator": "MA_CROSS_5_20", "operator": "CROSS_ABOVE", "value": 0},
        ],
        "market": "BOTH",
        "is_template": True,
    },
    {
        "name": "Mean Reversion (RSI)",
        "conditions": [
            {"indicator": "RSI", "operator": "<", "value": 25},
        ],
        "market": "BOTH",
        "is_template": True,
    },
    {
        "name": "Trend Following",
        "conditions": [
            {"indicator": "PRICE_ABOVE_MA200", "operator": "==", "value": 1},
            {"indicator": "MA_CROSS_5_20", "operator": "CROSS_ABOVE", "value": 0},
            {"indicator": "RSI", "operator": ">", "value": 40},
        ],
        "market": "BOTH",
        "is_template": True,
    },
    {
        "name": "Death Cross Short",
        "conditions": [
            {"indicator": "MA_CROSS_20_50", "operator": "CROSS_BELOW", "value": 0},
            {"indicator": "RSI", "operator": "<", "value": 50},
        ],
        "market": "BOTH",
        "is_template": True,
    },
]
