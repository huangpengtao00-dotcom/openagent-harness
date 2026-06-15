def get_cached(store, key, now):
    item = store.get(key)
    if item is None:
        return None
    return item["value"]
