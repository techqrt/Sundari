from django.shortcuts import render


def admin_chat_page(request):
    """Serves the Help Center admin chat UI. The page itself carries no data —
    it authenticates client-side against /auth/login/ and talks to the existing
    help_center admin API with the resulting JWT, same as any other client."""
    return render(request, 'help_center/admin_chat.html')
