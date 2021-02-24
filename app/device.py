import time
from flask import request, Blueprint, jsonify, abort, Response, send_file
import redis
import os
import json
from importlib import import_module
import sys

from .transcoder import transcoder
from .log import logger
from .utils import checkArgs, getUID, generateToken
from .dbHelper import getSqlConnection, r_userFiles, configData
from .devices.PlayerBase import PlayerBase

device = Blueprint("device", __name__)

fncts = {
    "play": (),
    "pause": (),
    "stop": (),
    "seek": ("position"),
    "setVolume": ("volume"),
    "mute": (),
    "unmute": (),
    "position": (),
    "loaded": (),
    "volume": (),
    "status": (),
    "playingMedia": (),
}


@device.route("supported")
def devices_supported():
    devs = []
    for i in os.listdir("app/devices/"):
        name = i[: i.rfind(".")]
        if i[i.rfind(".") + 1 :] == "py" and name != "PlayerBase":
            devs.append(name)

    return jsonify({"status": "ok", "data": devs})


@device.route("")
def devices_list():
    sqlConnection, cursor = getSqlConnection()
    cursor.execute("SELECT idDevice AS id, name, type, address, enabled FROM devices")
    data = cursor.fetchall()
    sqlConnection.close()
    for i in range(len(data)):
        data[i]["available"] = initDevice(data[i]).available

    return jsonify({"status": "ok", "data": data})


@device.route("<int:idDevice>")
def device_data(idDevice: int):
    sqlConnection, cursor = getSqlConnection()
    cursor.execute(
        "SELECT idDevice AS id, name, type, address, enabled FROM devices WHERE idDevice = %(idDevice)s",
        {"idDevice": idDevice},
    )
    data = cursor.fetchone()
    sqlConnection.close()
    data["available"] = os.system("ping -c 1 -W 1 " + data["address"]) == 0

    return jsonify({"status": "ok", "data": data})


@device.route("<int:idDevice>/function")
def devices_functions(idDevice: int):
    sqlConnection, cursor = getSqlConnection()
    cursor.execute(
        "SELECT type FROM devices WHERE idDevice = %(idDevice)s",
        {"idDevice": idDevice},
    )
    data = cursor.fetchone()
    sqlConnection.close()

    dev = importDevice(data["type"])

    return jsonify({"status": "ok", "data": list(set(fncts.keys()) & set(vars(dev)))})


@device.route("<int:idDevice>/function/<function>")
def devices_function(idDevice: int, function: str):
    if function in fncts.keys():
        args = {}
        for param in fncts[function]:
            if param not in request.args:
                abort(400)
            else:
                args[param] = request.args[param]

        sqlConnection, cursor = getSqlConnection()
        cursor.execute(
            "SELECT * FROM devices WHERE idDevice = %(idDevice)s",
            {"idDevice": idDevice},
        )
        data = cursor.fetchone()
        sqlConnection.close()

        if data["enabled"] == 0:
            return False
        device = initDevice(data)
        method = getattr(device, function)
        if callable(method):
            result = method(**args)
        else:
            result = method

        return jsonify({"status": "ok", "data": result})

    else:
        abort(400)


def initDevice(data) -> PlayerBase:
    dev = importDevice(data["type"])
    return dev(
        getUID(),
        request.args.get("token") or generateToken(getUID()),
        data.get("address"),
        data.get("port"),
        data.get("user"),
        data.get("password"),
        data.get("device"),
    )


def importDevice(devType: str):
    sys.path.append("app/devices/")
    if not os.path.exists("app/devices/" + devType + ".py"):
        return None
    module = import_module(devType)
    return getattr(module, devType)
