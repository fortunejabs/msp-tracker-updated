"""
Role-based access scoping helpers.
"""


def get_user_scope(user):
    """
    Returns (msp_name_or_None, province_or_None) based on user's role.
    Admins get full scope (None, None).
    """
    if not hasattr(user, 'profile'):
        return (None, None)

    p = user.profile
    if p.role == 'MSP' and p.msp:
        return (p.msp.name, None)
    if p.role == 'MANAGER' and p.province:
        return (None, p.province)
    return (None, None)


def scope_sites(queryset, user):
    """Apply role-based filtering to a Site queryset."""
    msp_name, province = get_user_scope(user)
    if msp_name:
        queryset = queryset.filter(msp__name=msp_name)
    if province:
        queryset = queryset.filter(province=province)
    return queryset


def scope_records(queryset, user):
    """Apply role-based filtering to MaintenanceRecord queryset"""
    msp, province = get_user_scope(user)
    if msp:
        queryset = queryset.filter(site__msp__name=msp)
    if province:
        queryset = queryset.filter(site__province=province)
    return queryset