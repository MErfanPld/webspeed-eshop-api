"""Drop the cached landing payload whenever its content changes."""
from django.core.cache import cache
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from .models import Article, FaqItem, LandingFeature, LandingSettings, Plan, RoadmapStep, Testimonial
from .services import LANDING_CACHE_KEY


@receiver([post_save, post_delete], sender=LandingSettings)
@receiver([post_save, post_delete], sender=LandingFeature)
@receiver([post_save, post_delete], sender=RoadmapStep)
@receiver([post_save, post_delete], sender=FaqItem)
@receiver([post_save, post_delete], sender=Testimonial)
@receiver([post_save, post_delete], sender=Article)
@receiver([post_save, post_delete], sender=Plan)
def clear_landing_cache(**kwargs):
    cache.delete(LANDING_CACHE_KEY)
