"""
Middleware for monitoring the LMS
"""
import logging
import re
from django.conf import settings
from edx_django_utils.monitoring import set_custom_metric

log = logging.getLogger(__name__)


class CodeOwnerMetricMiddleware:
    """
    Django middleware object to set custom metrics for the owner of each view.

    Custom metrics set:
    - code_owner: The owning team mapped to the current view.
    - code_owner_mapping_error: If there are any errors when trying to perform the mapping.
    - view_func_module: The __module__ of the view_func, which can be used to
        find missing mappings.

    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        return response

    def process_view(self, request, view_func, view_args, view_kwargs):
        """
        Set custom metric for the code_owner of the view if configured to do so.
        """
        if not _PATH_TO_CODE_OWNER_MAPPINGS:
            return

        try:
            view_func_module = _get_view_func_module(view_func)
            set_custom_metric('view_func_module', view_func_module)
            code_owner = self._find_code_owner(view_func_module)
            if code_owner:
                set_custom_metric('code_owner', code_owner)
        except Exception as e:
            set_custom_metric('code_owner_mapping_error', e)

    def _find_code_owner(self, view_func_module):
        """
        Attempts lookup of code_owner based on the view_func's __module__,
        finding the most specific match. If no match, returns None.

        For example, if the module were 'openedx.features.discounts.views',
        this lookup would match on 'openedx.features.discounts' before
        'openedx.features', because the former is more specific.

        """
        if _PATH_TO_CODE_OWNER_MAPPINGS is _INVALID_CODE_OWNER_MAPPING:
            raise Exception('CODE_OWNER_MAPPINGS django setting set with invalid configuration. See logs for details.')

        view_func_module_parts = view_func_module.split('.')
        # To make the most specific match, start with the max number of parts
        for number_of_parts in range(len(view_func_module_parts), 0, -1):
            partial_path = '.'.join(view_func_module_parts[0:number_of_parts])
            if partial_path in _PATH_TO_CODE_OWNER_MAPPINGS:
                code_owner = _PATH_TO_CODE_OWNER_MAPPINGS[partial_path]
                return code_owner
        return None


def _process_code_owner_mappings():
    """
    Processes the CODE_OWNER_MAPPINGS Django Setting and returns a dict optimized
    for efficient lookup by path.

    Returns:
         (dict): optimized dict for success processing, None if there are no
            configured mappings, or _INVALID_CODE_OWNER_MAPPING if there is an
            error processing the setting.

    Example CODE_OWNER_MAPPINGS Django Setting::

        CODE_OWNER_MAPPINGS = {
            'team-red': [
                'xblock_django',
                'openedx.core.djangoapps.xblock',
            ],
            'team-blue': [
                'badges',
            ],
        }

    Example return value::

        {
            'xblock_django': 'team-red',
            'openedx.core.djangoapps.xblock': 'team-red',
            'badges': 'team-blue',
        }

    """
    _CODE_OWNER_MAPPINGS = getattr(settings, 'CODE_OWNER_MAPPINGS', None)
    if not _CODE_OWNER_MAPPINGS:
        return None

    try:
        path_to_code_owner_mappings = {}
        for code_owner in _CODE_OWNER_MAPPINGS:
            path_list = _CODE_OWNER_MAPPINGS[code_owner]
            for path in path_list:
                path_to_code_owner_mappings[path] = code_owner
                optional_module_prefix_match = _OPTIONAL_MODULE_PREFIX_PATTERN.match(path)
                # if path has an optional prefix, also add the module name without the prefix
                if optional_module_prefix_match:
                    path_without_prefix = path[optional_module_prefix_match.end():]
                    path_to_code_owner_mappings[path_without_prefix] = code_owner

        return path_to_code_owner_mappings
    except Exception as e:
        log.exception('Error processing code_owner_mappings. {}'.format(e))
        # errors should be unlikely due do scripting the setting values.
        # this will trigger an error custom metric that can be alerted on.
        return _INVALID_CODE_OWNER_MAPPING

# .. toggle_name: CODE_OWNER_MAPPINGS
# .. toggle_implementation: DjangoSetting
# .. toggle_default: None
# .. toggle_description: Used to set monitoring custom metrics for owner. Dict with keys of code owner and value as list of dotted path module names owned by code owner.
# .. toggle_category: monitoring
# .. toggle_use_cases: open_edx
# .. toggle_creation_date: 2020-05-29
# .. toggle_expiration_date: None
# .. toggle_tickets: None
# .. toggle_status: supported
# .. toggle_warnings: None
# Set to settings.CODE_OWNER_MAPPINGS during processing for simpler testing
_CODE_OWNER_MAPPINGS = None

# The following module prefixes are optional in a func_view's reported module:
#   'common.djangoapps.', 'lms.djangoapps.', 'openedx.core.djangoapps.'
_OPTIONAL_MODULE_PREFIX_PATTERN = re.compile(r'^(lms|common|openedx\.core)\.djangoapps\.')
_INVALID_CODE_OWNER_MAPPING = 'invalid-code-owner-mapping'
# lookup table for code owner given a module path
_PATH_TO_CODE_OWNER_MAPPINGS = _process_code_owner_mappings()


def _get_view_func_module(view_func):
    """
    Returns the view_func's __module__.  Enables simpler testing via mocking.
    """
    return view_func.__module__
