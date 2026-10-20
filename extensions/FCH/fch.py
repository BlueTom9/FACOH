import json


class FCH:
    @staticmethod
    def turnjson(value):
        return json.dumps(value)

    @staticmethod
    def turnfch(json_text):
        return json.loads(json_text)
