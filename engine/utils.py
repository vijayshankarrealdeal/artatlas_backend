
def parse_result(cursor):
    results = []
    if isinstance(cursor, list) and len(cursor) > 0:
        for doc in cursor:
            doc["db_id"] = str(doc["_id"])
            del doc["_id"]
            results.append(doc)
        return results
    cursor['db_id'] = str(cursor['_id'])
    del cursor['_id']
    return cursor