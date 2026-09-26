import re

VARIABLES = {
    "customer.id",
    "customer.name",
    "comment.id",
    "comment.text",
    "product.name",
    "product.description",
    "product.sku",
    "product.availability",
    "product.base_price",
    "product.base_currency",
    "product.price",
    "product.currency",
    "product.converted_price",
    "product.original_price",
    "product.discount",
    "product.url",
    "exchange.rate",
    "exchange.source",
    "exchange.updated_at",
    "instagram.username",
    "media.caption",
    "media.url",
}
TOKEN = re.compile(r"{{\s*([a-z_]+\.[a-z_]+)\s*}}")


def validate_template(template: str):
    if len(template) > 1000:
        raise ValueError("template_too_long")
    if any(name not in VARIABLES for name in TOKEN.findall(template)):
        raise ValueError("unknown_template_variable")
    remainder = TOKEN.sub("", template)
    if any(marker in remainder for marker in ("{{", "}}", "{%", "{#")):
        raise ValueError("invalid_template")


def render(template: str, context: dict) -> str:
    validate_template(template)

    def replace(match):
        group, name = match.group(1).split(".")
        if group not in context or name not in context[group]:
            raise ValueError("template_context_missing")
        return str(context[group][name])

    result = TOKEN.sub(replace, template)
    if len(result) > 1000:
        raise ValueError("rendered_message_too_long")
    return result
