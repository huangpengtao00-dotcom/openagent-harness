def create_post(existing_slugs, slug):
    existing_slugs.add(slug)
    return {"status": 201, "slug": slug}
