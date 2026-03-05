from typing import Literal, NotRequired, TypedDict


class DeviceInfo(TypedDict):
    ip: str
    mac: NotRequired[str]
    cpu: NotRequired[str]
    memory: NotRequired[str]
    disk: NotRequired[str]
    network: NotRequired[str]
    version: NotRequired[str]
    name: NotRequired[str]
    status: NotRequired[str]
    indexNum: NotRequired[int]


class CloudConfig(TypedDict):
    name: str
    newName: NotRequired[str]
    command: NotRequired[list[str]]
    imageUrl: NotRequired[str]
    modelId: NotRequired[str]
    dns: NotRequired[str]
    network: NotRequired[str]
    localModel: NotRequired[bool]
    countryCode: NotRequired[str]
    s5Proxy: NotRequired[dict[str, object]]


class ImageConfig(TypedDict):
    name: str
    imageUrl: NotRequired[str]
    modelId: NotRequired[str]
    localModel: NotRequired[bool]
    countryCode: NotRequired[str]
    dns: NotRequired[str]
    network: NotRequired[str]
    suffix: NotRequired[str]


class ProxyConfig(TypedDict):
    s5IP: str
    s5Port: int
    s5User: str
    s5Password: str
    s5Type: NotRequired[int]
    ip: NotRequired[str]
    port: NotRequired[int]
    usr: NotRequired[str]
    pwd: NotRequired[str]
    type: NotRequired[int]
    domains: NotRequired[list[str]]


class SDKResponse(TypedDict):
    ok: bool
    data: NotRequired[object]
    error: NotRequired[str]
    message: NotRequired[str]
    status: NotRequired[Literal["success", "failed", "error", "timeout"]]
