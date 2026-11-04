from rest_framework.pagination import PageNumberPagination


class StandardPagination(PageNumberPagination):
    """Default 25 per page; list pages can ask for more with ``?page_size=`` (max 500)."""

    page_size_query_param = "page_size"
    max_page_size = 500
