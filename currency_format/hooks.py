# Copyright 2026 Daniel Lo Nigro
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).

from types import FunctionType

from odoo.tools import misc

from .defaults import get_default_spacing_for_currency
from .formatting import apply_symbol_spacing

_PATCH_MARKER = "_currency_format_patched"
_HELPER_NAME = "_currency_format_apply_symbol_spacing"
_ORIGINAL_FORMAT_AMOUNT = "_currency_format_original_format_amount"
_ORIGINAL_FORMAT_LANG = "_currency_format_original_format_lang"


def _patched_format_amount(env, amount, currency, lang_code=None):
    formatted = _currency_format_original_format_amount(  # noqa: F821
        env, amount, currency, lang_code
    )
    return _currency_format_apply_symbol_spacing(formatted, currency)  # noqa: F821


def _patched_format_lang(
    env,
    value,
    digits=2,
    grouping=True,
    monetary=misc.SENTINEL,
    dp=None,
    currency_obj=None,
    rounding_method="HALF-EVEN",
    rounding_unit="decimals",
):
    formatted = _currency_format_original_format_lang(  # noqa: F821
        env,
        value,
        digits,
        grouping,
        monetary,
        dp,
        currency_obj,
        rounding_method,
        rounding_unit,
    )
    if not currency_obj:
        return formatted
    return _currency_format_apply_symbol_spacing(formatted, currency_obj)  # noqa: F821


def _clone_function(function):
    # Preserve the original implementation before _patch_function replaces its code.
    # Reuse its globals, defaults, and closure so the clone behaves identically.
    clone = FunctionType(
        function.__code__,
        function.__globals__,
        function.__name__,
        function.__defaults__,
        function.__closure__,
    )
    # FunctionType does not accept keyword-only defaults in its constructor.
    clone.__kwdefaults__ = function.__kwdefaults__
    return clone


def _patch_function(function, replacement, original_name):
    if getattr(function, _PATCH_MARKER, False):
        return

    # Keep an unmodified callable for the replacement to delegate to.
    function.__globals__[original_name] = _clone_function(function)
    # Replacing __code__ does not replace __globals__, so expose the helper there.
    function.__globals__[_HELPER_NAME] = apply_symbol_spacing
    # Mutate the function in place so existing direct imports use the patch too.
    function.__code__ = replacement.__code__
    setattr(function, _PATCH_MARKER, True)


def post_load():
    """Patch utility functions in place so existing direct imports are updated."""
    _patch_function(
        misc.format_amount,
        _patched_format_amount,
        _ORIGINAL_FORMAT_AMOUNT,
    )
    _patch_function(
        misc.formatLang,
        _patched_format_lang,
        _ORIGINAL_FORMAT_LANG,
    )


def post_init_hook(env):
    """On installation, set the default symbol spacing for existing currencies."""
    currencies = env["res.currency"].with_context(active_test=False).search([])
    for currency in currencies:
        if not currency.symbol_spacing:
            currency.symbol_spacing = get_default_spacing_for_currency(currency.name)
