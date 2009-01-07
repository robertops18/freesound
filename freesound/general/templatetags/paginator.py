import urllib
from django import template

register = template.Library()

@register.inclusion_tag('templatetags/paginator.html', takes_context=True)
def show_paginator(context, paginator, page, current_page, request, anchor=""):
    """
    Adds pagination context variables for use in displaying first, adjacent and
    last page links in addition to those created by the object_list generic
    view.
    """

    adjacent_pages = 3
    total_wanted = adjacent_pages * 2 + 1
    min_page_num = max(current_page - adjacent_pages, 1)
    max_page_num = min(current_page + adjacent_pages + 1, paginator.num_pages + 1)

    num_items = max_page_num - min_page_num

    if num_items < total_wanted and num_items < paginator.num_pages:
        if min_page_num == 1:
            # we're at the start, increment max_page_num
            max_page_num += min(total_wanted - num_items, paginator.num_pages - num_items)
        else:
            # we're at the end, decrement
            min_page_num -= min(total_wanted - num_items, paginator.num_pages - num_items)

    # although paginator objects are 0-based, we use 1-based paging
    page_numbers = [n for n in range(min_page_num, max_page_num) if n > 0 and n <= paginator.num_pages]
    
    params = urllib.urlencode([(key, value.encode('utf-8')) for (key, value) in request.GET.items() if key.lower() != u"page"])
    
    if params == "":
        url = request.path + u"?page="
    else:
        url = request.path + u"?" + params + u"&page="

    return {
        "page": page,
        "paginator": paginator,
        "current_page": current_page,
        "page_numbers": page_numbers,
        "show_first": 1 not in page_numbers,
        "show_last": paginator.num_pages not in page_numbers,
        "url" : url,
        "media_url": context['media_url'],
        "anchor": anchor
    }