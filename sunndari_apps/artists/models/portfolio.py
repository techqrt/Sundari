import os
import uuid

from django.db import models
from django.db.models import Q
from django.utils import timezone


def portfolio_upload_path(instance, filename):
    extension = os.path.splitext(filename)[1].lower()
    return f'portfolios/artist_{instance.artist_id}/{uuid.uuid4().hex}{extension}'


class Portfolio(models.Model):
    MEDIA_TYPE_CHOICES = [('image', 'Image'), ('video', 'Video')]

    portfolio_id = models.AutoField(primary_key=True)
    artist = models.ForeignKey(
        'artists.ArtistProfile',
        on_delete=models.CASCADE,
        related_name='portfolios',
    )
    file = models.FileField(upload_to=portfolio_upload_path)
    media_type = models.CharField(max_length=10, choices=MEDIA_TYPE_CHOICES)
    sub_category = models.ForeignKey(
        'core.ServiceSubCategory',
        on_delete=models.PROTECT,
        related_name='portfolios',
    )
    caption = models.CharField(max_length=300, null=True, blank=True)
    approval_status = models.ForeignKey(
        'core.ApprovalStatus',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
    )
    is_active = models.BooleanField(default=True)
    # Work samples are photos submitted for admin review during onboarding (max 5 per artist);
    # they are not part of the public portfolio.
    is_work_sample = models.BooleanField(default=False)
    # Display order inside the artist's portfolio (lower first); new items go to the end.
    sort_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'portfolios'

    def __str__(self):
        return f"Portfolio #{self.portfolio_id} (Artist #{self.artist_id})"

    @staticmethod
    def count_active(artist_id: int) -> int:
        return Portfolio.objects.filter(artist_id=artist_id, is_active=True, is_work_sample=False).count()

    @staticmethod
    def reorder(artist_id: int, ordered_ids: list) -> None:
        """Puts the given items first, in the given order; any item not listed keeps its
        existing relative order after them."""
        listed = {pid: index for index, pid in enumerate(ordered_ids)}
        rest = list(
            Portfolio.objects.filter(artist_id=artist_id).exclude(portfolio_id__in=ordered_ids)
            .order_by('sort_order', 'portfolio_id').values_list('portfolio_id', flat=True)
        )
        position = {**listed, **{pid: len(ordered_ids) + i for i, pid in enumerate(rest)}}
        for portfolio_id, order in position.items():
            Portfolio.objects.filter(portfolio_id=portfolio_id, artist_id=artist_id).update(sort_order=order)

    @staticmethod
    def count_work_samples(artist_id: int) -> int:
        return Portfolio.objects.filter(artist_id=artist_id, is_active=True, is_work_sample=True).count()

    def create(self, artist_id: int, file, media_type: str, sub_category_id: int, caption: str = None, is_work_sample: bool = False) -> int:
        from sunndari_apps.core.models.approval_status import ApprovalStatus
        pending = ApprovalStatus.objects.filter(name='pending').first()
        self.artist_id = artist_id
        self.file = file
        self.media_type = media_type
        self.sub_category_id = sub_category_id
        self.caption = caption
        self.is_work_sample = is_work_sample
        self.sort_order = (Portfolio.objects.filter(artist_id=artist_id).aggregate(models.Max('sort_order'))['sort_order__max'] or 0) + 1
        self.approval_status = pending
        self.save()
        return self.portfolio_id

    @staticmethod
    def update(portfolio_id: int, caption: str = None, sub_category_id: int = None, is_active: bool = None) -> None:
        item = Portfolio.objects.get(portfolio_id=portfolio_id)
        if caption is not None:
            item.caption = caption
        if sub_category_id is not None:
            item.sub_category_id = sub_category_id
        if is_active is not None:
            item.is_active = is_active
        item.save()

    @staticmethod
    def remove(portfolio_id: int) -> None:
        item = Portfolio.objects.get(portfolio_id=portfolio_id)
        stored = item.file
        item.delete()
        if stored:
            stored.delete(save=False)          # the row owns its media file

    @staticmethod
    def get(portfolio_id: int) -> dict:
        return Portfolio.objects.filter(portfolio_id=portfolio_id).values(
            'portfolio_id', 'artist_id', 'file', 'media_type', 'sub_category_id',
            'caption', 'approval_status_id', 'is_active', 'is_work_sample', 'sort_order', 'created_at', 'updated_at',
        ).first()

    @staticmethod
    def get_all(
        artist_id: int,
        sort_by: str = '',
        sort_order: str = 'asc',
        filter_key: str = '',
        filter_value: str = '',
        search_key: str = '',
        include_work_samples: bool = True,
        only_active: bool = False,
    ) -> list:
        data = Portfolio.objects.filter(artist_id=artist_id)
        if only_active:
            data = data.filter(is_active=True)
        if not include_work_samples:
            data = data.exclude(is_work_sample=True)
        if filter_key and filter_value:
            lookup = '__exact' if filter_value.isdigit() else '__icontains'
            data = data.filter(**{f'{filter_key}{lookup}': filter_value})
        if search_key:
            data = data.filter(Q(caption__icontains=search_key) | Q(media_type__icontains=search_key))
        if sort_by:
            data = data.order_by(('-' if sort_order == 'desc' else '') + sort_by)
        else:
            data = data.order_by('sort_order', 'portfolio_id')
        return list(data.values(
            'portfolio_id', 'artist_id', 'file', 'media_type', 'sub_category_id',
            'caption', 'approval_status_id', 'is_active', 'is_work_sample', 'sort_order', 'created_at', 'updated_at',
        ))
