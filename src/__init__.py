"""
Source package for DevOps Project Template Builder.
"""

from .devops_client import DevOpsClient
from .hierarchy_service import (
    fetch_hierarchy,
    prune_to_subtree,
    build_tree,
    compute_summary,
    format_tree_text,
    tree_to_yaml_structure,
    clean_html,
)
from .models import (
    EpicItem,
    FeatureItem,
    StoryItem,
    TaskItem,
    ProjectData,
    WORK_ITEM_MODELS,
    build_work_item_data,
)
from .template_service import (
    load_template,
    expand_all_features,
    save_yaml,
    lint_yaml,
    validate_template,
    count_work_items,
    parse_instance_overrides,
    apply_instance_overrides,
    exclude_features,
    slugify,
)
from .upload_service import upload_from_yaml

__all__ = [
    'DevOpsClient',
    'fetch_hierarchy', 'prune_to_subtree', 'build_tree', 'compute_summary',
    'format_tree_text', 'tree_to_yaml_structure', 'clean_html',
    'EpicItem', 'FeatureItem', 'StoryItem', 'TaskItem', 'ProjectData',
    'WORK_ITEM_MODELS', 'build_work_item_data',
    'load_template', 'expand_all_features', 'save_yaml', 'lint_yaml',
    'validate_template', 'count_work_items', 'parse_instance_overrides',
    'apply_instance_overrides', 'exclude_features', 'slugify',
    'upload_from_yaml',
]
