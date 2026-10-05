from django.urls import path
from sunndari_apps.admin_panel.controllers.artist_review import AdminArtistReviewController
from sunndari_apps.admin_panel.controllers.artist_document import AdminArtistDocumentController
from sunndari_apps.admin_panel.controllers.brand import AdminBrandController

urlpatterns = [
    # Artist Review (onboarding approval)
    path('artists/review_queue/get_all/', AdminArtistReviewController.get_all_review_queue, name='admin_get_all_review_queue'),
    path('artists/review/get/', AdminArtistReviewController.get_review_detail, name='admin_get_artist_review_detail'),
    path('artists/approve/', AdminArtistReviewController.approve_artist, name='admin_approve_artist'),
    path('artists/documents/get_all/', AdminArtistDocumentController.get_all_documents, name='admin_get_all_artist_documents'),
    path('artists/documents/verify/', AdminArtistDocumentController.verify_document, name='admin_verify_artist_document'),
    path('brands/create/', AdminBrandController.create_brand, name='admin_create_brand'),
    path('brands/update/', AdminBrandController.update_brand, name='admin_update_brand'),
    path('brands/requests/get_all/', AdminBrandController.get_all_requests, name='admin_get_all_brand_requests'),
    path('brands/requests/decide/', AdminBrandController.decide_request, name='admin_decide_brand_request'),
    path('artists/reject/', AdminArtistReviewController.reject_artist, name='admin_reject_artist'),
]
