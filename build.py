#   -*- coding: utf-8 -*-
from pybuilder.core import use_plugin, init

use_plugin("python.core")
use_plugin("python.unittest")
#use_plugin("python.coverage")
use_plugin("python.distutils")

name = "vaccine_tracker_telegram_bot"
default_task = "publish"


@init
def set_properties(project):
    pass
