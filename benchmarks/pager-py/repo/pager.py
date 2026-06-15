def page(items, number, size):
    start = number * size
    end = start + size
    return items[start:end]
