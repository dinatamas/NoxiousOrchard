import asyncio
import dataclasses
import json


class Dispatcher:
    def __init__(self):
        self.methods = dict()
        self.queue = asyncio.PriorityQueue()

    def register(self, function, name=None):
        name = name or function.__name__
        if name.startswith("do_"):
            name = name[3:]
        self.methods[name] = function

    def feed(self, rpc):
        pass

    async def take(self):
        pass


@dataclasses.dataclass
class RPC:
    state: str
    id: int | None = None
    method: str | None = None
    message: str | None = None
    args: list | None = None
    kwargs: dict | None = None
    results: list | None = None
    error: Exception | None = None
    future: asyncio.Future | None = None

    async def wait(self):
        if self.future:
            await asyncio.wait(self.future)
            return self.results
        return None

    ############################################
    # instance serialization / deserialization #
    ############################################

    def dump(self):
        data = dataclasses.asdict(self)
        data["error"] = self.dump_error(data["error"])
        del data["future"]
        return json.dumps(data)

    @classmethod
    def parse(cls, rpc):
        try:
            return cls._parse(rpc)
        except Exception as e:
            return json.dumps({"ack": False, **cls.dump_error(e)}), None
    @classmethod
    def _parse(cls, rpc):
        ack = json.dumps({"ack": True})
        rpc = json.loads(rpc)
        rpc["error"] = cls.parse_error(rpc)
        if "ack" in rpc:
            if rpc["ack"]:
                return None, None
            else:
                return None, cls(state="ack", error=rpc["error"])
        return ack, cls(**rpc)

    #############################################
    # component serialization / deserialization #
    #############################################

    @staticmethod
    def dump_error(err):
        if isinstance(err, json.JSONDecodeError):
            data = {"msg": err.msg, "doc": err.doc, "pos": err.pos}
            return {"error": {"message": "JSONDecodeError", "data": data}}
        else:
            raise ValueError(f"Unknown error: {repr(err)}")

    @staticmethod
    def parse_error(rpc):
        if "error" not in rpc:
            return None
        if rpc["error"]["message"] == "JSONDecodeError":
            msg = rpc["error"]["data"]["msg"]
            doc = rpc["error"]["data"]["doc"]
            pos = rpc["error"]["data"]["pos"]
            return json.JSONDecodeError(msg, doc, pos)
        else:
            raise ValueError(f"Unknown error: {rpc['error']['message']}")
