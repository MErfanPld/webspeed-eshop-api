from django.core.management.base import BaseCommand

from apps.core.seed import ensure_seeded


class Command(BaseCommand):
    help = "Create the default store, owner account, pages and sample catalog (idempotent)."

    def handle(self, *args, **options):
        created, generated = ensure_seeded()
        if not created:
            self.stdout.write("Already seeded — nothing to do.")
            return
        self.stdout.write(self.style.SUCCESS("Seeded default store, owner, pages, 8 categories and 20 products."))
        if generated:
            # Printed once to the console only (never logged to files)
            self.stdout.write(self.style.WARNING(f"Generated owner password: {generated}  (change it after login)"))
