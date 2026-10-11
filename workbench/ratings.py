"""Reviewed default ratings, ordered from low to high.

Existing report values and custom item wording remain unchanged.
"""
DEFAULT_RATING_OPTIONS = {
    'likelihood': ['Unlikely', 'Possible', 'Likely'],
    'severity': ['Negligible', 'Minor', 'Moderate', 'Severe'],
    'priority': ['Low', 'Moderate', 'High', 'Urgent'],
}
PRIORITY_OPTIONS = DEFAULT_RATING_OPTIONS['priority']
# Cost rows created with earlier versions must still validate and export.
LEGACY_COST_PRIORITIES = ['Critical']
