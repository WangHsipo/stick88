import ast
import math
import re


NO_PROTOCOL = "不使用协议"
MAX_TEXT_LENGTH = 15


DEFAULT_PROTOCOLS = [
    {
        "name": "ANF输入输出",
        "channels": {
            "1": {"enabled": True, "data_name": "ANF输入误差", "gain": "1", "bias": "0", "unit": "V", "display_ticks": "[]"},
            "2": {"enabled": True, "data_name": "ANF六倍频输出", "gain": "1", "bias": "0", "unit": "V", "display_ticks": "[]"},
        },
    },
    {
        "name": "六倍频分析",
        "channels": {
            "1": {"enabled": True, "data_name": "六倍频相位", "gain": "360/1.25", "bias": "0", "unit": "°", "display_ticks": "[0, 360]"},
            "2": {"enabled": True, "data_name": "六倍频幅值", "gain": "0.5/(2.5-1.25)", "bias": "1.25", "unit": "pu", "display_ticks": "[0, 0.5]"},
            "3": {"enabled": True, "data_name": "电流", "gain": "1", "bias": "0", "unit": "A", "display_ticks": "[]"},
        },
    },
    {
        "name": "角度分析",
        "channels": {
            "1": {"enabled": True, "data_name": "角度误差", "gain": "10/0.5", "bias": "1.25", "unit": "°", "display_ticks": "[-10, 10, 0]"},
            "2": {"enabled": True, "data_name": "编码器角度", "gain": "360/1.25", "bias": "0", "unit": "°", "display_ticks": "[0, 360]"},
            "3": {"enabled": True, "data_name": "电流", "gain": "1", "bias": "0", "unit": "A", "display_ticks": "[]"},
        },
    },
]


ALLOWED_BINARY_OPERATORS = {
    ast.Add: lambda a, b: a + b,
    ast.Sub: lambda a, b: a - b,
    ast.Mult: lambda a, b: a * b,
    ast.Div: lambda a, b: a / b,
    ast.FloorDiv: lambda a, b: a // b,
    ast.Mod: lambda a, b: a % b,
    ast.Pow: lambda a, b: a**b,
}
ALLOWED_UNARY_OPERATORS = {
    ast.UAdd: lambda value: value,
    ast.USub: lambda value: -value,
}


def evaluate_expression(expression):
    text = str(expression).strip()
    if not text:
        raise ValueError("表达式不能为空。")
    if len(text) > 80:
        raise ValueError("表达式过长。")
    try:
        tree = ast.parse(text, mode="eval")
    except SyntaxError as exc:
        raise ValueError(f"表达式格式错误: {text}") from exc

    def evaluate(node):
        if isinstance(node, ast.Expression):
            return evaluate(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return float(node.value)
        if isinstance(node, ast.BinOp) and type(node.op) in ALLOWED_BINARY_OPERATORS:
            return ALLOWED_BINARY_OPERATORS[type(node.op)](evaluate(node.left), evaluate(node.right))
        if isinstance(node, ast.UnaryOp) and type(node.op) in ALLOWED_UNARY_OPERATORS:
            return ALLOWED_UNARY_OPERATORS[type(node.op)](evaluate(node.operand))
        raise ValueError("只允许数字、括号和 + - * / // % ** 运算符。")

    try:
        result = float(evaluate(tree))
    except (ArithmeticError, OverflowError) as exc:
        raise ValueError(f"表达式无法计算: {text}") from exc
    if not math.isfinite(result):
        raise ValueError("表达式结果必须是有限数值。")
    return result


def validate_short_text(value, label, allow_empty=False):
    text = str(value).strip()
    if not text and not allow_empty:
        raise ValueError(f"{label}不能为空。")
    if len(text) > MAX_TEXT_LENGTH:
        raise ValueError(f"{label}不能超过 {MAX_TEXT_LENGTH} 个字符。")
    if any(ord(char) < 32 for char in text):
        raise ValueError(f"{label}包含无效字符。")
    return text


def parse_display_ticks(expression):
    text = str(expression).strip() or "[]"
    if len(text) > 120:
        raise ValueError("显示刻度数组过长。")
    try:
        tree = ast.parse(text, mode="eval")
    except SyntaxError as exc:
        raise ValueError("显示刻度必须是数组，例如 [-10, 0, 10]。") from exc
    if not isinstance(tree.body, ast.List):
        raise ValueError("显示刻度必须使用数组，例如 [0, 360]。")
    if len(tree.body.elts) > 5:
        raise ValueError("每个通道最多设置 5 个显示刻度。")
    values = []
    for element in tree.body.elts:
        try:
            value = evaluate_expression(ast.unparse(element))
        except (ValueError, AttributeError) as exc:
            raise ValueError("显示刻度只能包含数值或算术表达式。") from exc
        if value not in values:
            values.append(value)
    return text, values


def normalize_channel_config(config):
    config = config if isinstance(config, dict) else {}
    enabled = bool(config.get("enabled", False))
    data_name = validate_short_text(config.get("data_name", ""), "数据名称", allow_empty=not enabled)
    unit = validate_short_text(config.get("unit", ""), "单位", allow_empty=not enabled)
    gain_text = str(config.get("gain", "1")).strip() or "1"
    bias_text = str(config.get("bias", "0")).strip() or "0"
    display_ticks_text, display_ticks_values = parse_display_ticks(config.get("display_ticks", "[]"))
    gain_value = evaluate_expression(gain_text)
    bias_value = evaluate_expression(bias_text)
    if enabled and gain_value == 0:
        raise ValueError("换算系数不能为 0。")
    return {
        "enabled": enabled,
        "data_name": data_name,
        "gain": gain_text,
        "gain_value": gain_value,
        "bias": bias_text,
        "bias_value": bias_value,
        "unit": unit,
        "display_ticks": display_ticks_text,
        "display_ticks_values": display_ticks_values,
    }


def normalize_protocol(protocol):
    protocol = protocol if isinstance(protocol, dict) else {}
    name = validate_short_text(protocol.get("name", ""), "协议名称")
    source_channels = protocol.get("channels", {})
    channels = {}
    for channel in range(1, 5):
        normalized = normalize_channel_config(source_channels.get(str(channel), {}))
        if normalized["enabled"]:
            channels[str(channel)] = normalized
    if not channels:
        raise ValueError("协议至少要启用一个通道。")
    return {"name": name, "channels": channels}


def normalize_protocols(protocols):
    normalized = []
    names = set()
    for protocol in protocols if isinstance(protocols, list) else []:
        item = normalize_protocol(protocol)
        if item["name"] in names:
            raise ValueError(f"协议名称重复: {item['name']}")
        names.add(item["name"])
        normalized.append(item)
    return normalized


def protocols_for_storage(protocols):
    stored = []
    for protocol in normalize_protocols(protocols):
        channels = {}
        for channel, config in protocol["channels"].items():
            channels[channel] = {
                "enabled": True,
                "data_name": config["data_name"],
                "gain": config["gain"],
                "bias": config["bias"],
                "unit": config["unit"],
                "display_ticks": config["display_ticks"],
            }
        stored.append({"name": protocol["name"], "channels": channels})
    return stored


def find_protocol(protocols, name):
    if not name or name == NO_PROTOCOL:
        return None
    for protocol in protocols:
        if protocol.get("name") == name:
            return normalize_protocol(protocol)
    return None


def csv_identifier(text, fallback="value"):
    cleaned = re.sub(r"\W+", "_", str(text).strip(), flags=re.UNICODE).strip("_")
    return cleaned or fallback


def apply_conversion(value, channel_config):
    return (value - channel_config["bias_value"]) * channel_config["gain_value"]
