from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    CategoryViewSet, ProductViewSet, FAQViewSet, TestimonialViewSet,
    LandingVideoViewSet, LandingStepViewSet, ContactView,
)

router = DefaultRouter()
router.register(r'categories', CategoryViewSet)
router.register(r'products', ProductViewSet, basename='product')
router.register(r'faqs', FAQViewSet, basename='faq')
router.register(r'testimonials', TestimonialViewSet, basename='testimonial')
router.register(r'landing-videos', LandingVideoViewSet, basename='landing-video')
router.register(r'landing-steps', LandingStepViewSet, basename='landing-step')

urlpatterns = [
    path('contacto/', ContactView.as_view(), name='contact'),
    path('', include(router.urls)),
]
