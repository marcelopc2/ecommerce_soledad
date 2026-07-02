from django.http import JsonResponse

def health_check(request):
    return JsonResponse({
        "status": "ok",
        "message": "IngenioBlocks E-Commerce API is running!",
        "version": "1.0.0"
    })
