#!/usr/bin/env python
# -*- coding: utf-8 -*-
# This program is dedicated to the public domain under the CC0 license.
from multiprocessing.queues import Queue
from telegram.ext.callbackqueryhandler import CallbackQueryHandler

"""
Simple Bot to reply to Telegram messages.
First, a few handler functions are defined. Then, those functions are passed to
the Dispatcher and registered at their respective places.
Then, the bot is started and runs until we press Ctrl-C on the command line.
Usage:
Basic Echobot example, repeats messages.
Press Ctrl-C on the command line or send a signal to the process to stop the
bot.
"""

import logging, requests, json, schedule, threading
import polling2, queue
from telegram import ReplyKeyboardMarkup, ReplyKeyboardRemove, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Updater,
    CommandHandler,
    MessageHandler,
    Filters,
    ConversationHandler,
    CallbackQueryHandler,
    CallbackContext,
)

# Enable logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    level=logging.INFO)

logger = logging.getLogger(__name__)

SELECTING_ACTION, SELECTING_PIN, SELECTING_LOCATION, PIN, LOCATION, DATE, PROCESS = map(chr, range(7))
dict = {"1":PIN, "2":LOCATION}
END = ConversationHandler.END

responseQueue = queue.SimpleQueue()


class RequestParams(object):
    pin = ""
    date = None
    latitude = None
    longitude = None
    type = None

    # The class "constructor" - It's actually an initializer 
    def __init__(self, type, pin=None, date=None, latitude=None, longitude=None):
        self.type = type
        self.pin = pin
        self.date = date
        self.longitude = longitude
        self.latitude = latitude

        
class Response(object):
    json_obj = None
    type = None

    # The class "constructor" - It's actually an initializer 
    def __init__(self, type, json_obj):
        self.type = type
        self.json_obj = json_obj


# Define a few command handlers. These usually take the two arguments update and
# context. Error handlers also receive the raised TelegramError object in error.
def start(update, context) -> None:
    """Send a message when the command /start is issued."""
    buttons = [
        [
            InlineKeyboardButton(text='Search via Pin Code', callback_data=str(PIN)),
            InlineKeyboardButton(text='Search via Location', callback_data=str(LOCATION)),
        ],
        [
            InlineKeyboardButton(text='Already vaccinated !', callback_data=str(END)),
        ],
    ]

    keyboard = InlineKeyboardMarkup(buttons)
    # update.message.reply_text('Hello !\nWelcome to Vaccine Tracker\nPlease provide pin', reply_markup=ReplyKeyboardRemove())
    update.message.reply_text('Hello !\nWelcome to Vaccine Tracker\nPlease choose:', reply_markup=keyboard)
    return SELECTING_ACTION


def help(update, context):
    """Send a message when the command /help is issued."""
    update.message.reply_text('Help!')


def cancel(update: Update, _: CallbackContext) -> int:
    user = update.message.from_user
    logger.info("User %s canceled the conversation.", user.first_name)
    update.message.reply_text(
        'Bye! ', reply_markup=ReplyKeyboardRemove()
    )

    return ConversationHandler.END


def date(update: Update, _: CallbackContext) -> int:
    user = update.message.from_user
    _.user_data['date'] = update.message.text
    logger.info("Date provided by %s: %s", user.first_name, update.message.text)
    update.message.reply_text(
            'Thanks, we will notify you as soon as a slot is available for this date.\nTo unsubscribe, type in /vaccinated',
        reply_markup=ReplyKeyboardRemove(),
    )
    complete(update, _)
    return ConversationHandler.END


def pin(update: Update, _: CallbackContext) -> int:
    user = update.message.from_user
    _.user_data['requestType'] = 'PIN'
    _.user_data['pin'] = update.message.text
    logger.info("Pin of %s: %s", user.first_name, update.message.text)
    update.message.reply_text('Please provide the date in format DD-MM-YYYY',
        reply_markup=ReplyKeyboardRemove(),
    )
    return DATE


def location(update: Update, _: CallbackContext) -> int:
    user = update.message.from_user
    _.user_data['requestType'] = 'LOCATION'
    _.user_data['location'] = update.message.location
    logger.info("Location of %s: %s - %s", user.first_name, update.message.location.latitude, update.message.location.longitude)
    update.message.reply_text(
            'Thanks, we will notify you as soon as a slot is available for this date.\nTo unsubscribe, type in /vaccinated',
        reply_markup=ReplyKeyboardRemove(),
    )
    complete(update, _)
    return ConversationHandler.END


def isSuccess(res: Response) -> bool:
    found = False;
    json_obj = res.json_obj
    logger.info("Response: %s", json_obj)
    names = []
    if json_obj is not None:
        s1 = json.dumps(json_obj)
        result = json.loads(s1)
        key = None
        if(res.type == 'PIN'):
            key = 'sessions'
        else:
            key = 'centers'
        for centre in result[key]:
            # if centre['name']=="DGD Bank Enclave PHC":
            names.append(centre['name'])
            # responseQueue.put_nowait(centre['name'])
            found = True
    if found:
        msg = "Following centres are available:\n\n"
        msg += '\n'.join(names)
        responseQueue.put_nowait(msg)
    return found


def createPinCodeParams(context, type) -> RequestParams:
    pin = context.user_data['pin']
    date = context.user_data['date']
    params = RequestParams(type, pin=pin, date=date)
    return params


def createLocationParams(context:CallbackContext, type) -> RequestParams:
    location = context.user_data['location']
    params = RequestParams(type, latitude=location.latitude, longitude=location.longitude)
    return params


def complete(update: Update, context: CallbackContext):
    user = update.message.from_user
    type = context.user_data['requestType']
    params = None
    if(type == 'PIN'):
        params = createPinCodeParams(context, type)
    else:
        params = createLocationParams(context, type)
    
    logger.info("Nominated person: %s, Parameters: %s", user.first_name, params)

    def run_threaded(job_func):
        job_thread = threading.Thread(target=job_func)
        job_thread.start()

    polling2.poll(target=lambda:checkDetails(params), check_success=isSuccess, step=10,
    timeout=3600,
    log=logging.DEBUG)
    run_threaded(sendMessage(update))


def sendMessage(update: Update):
    while True:
        res = responseQueue.get(block=True)
        # x = json.loads(data, object_hook=lambda d: SimpleNamespace(**d))
        # prettyPrint=json.dumps(res)
        update.message.reply_text(res,
                                      reply_markup=ReplyKeyboardRemove(),)
        break
        

def vaccinated(update: Update, _: CallbackContext) -> int:
    user = update.message.from_user
    logger.info("Vaccinated person: %s", user.first_name)
    update.message.reply_text(
        'Thanks for using this service !',
        reply_markup=ReplyKeyboardRemove(),
    )
    return ConversationHandler.END


def checkDetails(param: RequestParams):
    """Echo the user message."""
    type = param.type
    if(type == 'PIN'):
        return makePinCodeRequest(param)     
    else:
        return makeLocationRequest(param)


def makeHeader() -> str:
    header = {'Accept-Language': 'hi_IN', 'Accept': 'application/json', 'user-agent':'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/90.0.4430.93 Safari/537.36'}
    return header


def makePinCodeRequest(param:RequestParams):
    pload = {'pincode':param.pin, 'date':param.date}
    response = requests.get('https://cdn-api.co-vin.in/api/v2/appointment/sessions/public/findByPin', params=pload, headers=makeHeader())
    res = Response(param.type, response.json())
    return res;


def makeLocationRequest(param:RequestParams):
    pload = {'lat':param.latitude, 'long':param.longitude}
    response = requests.get('https://cdn-api.co-vin.in/api/v2/appointment/centers/public/findByLatLong', params=pload, headers=makeHeader())
    res = Response(param.type, response.json())
    return res;


def error(update, context):
    """Log Errors caused by Updates."""
    logger.warning('Update "%s" caused error "%s"', update, context.error)


def select_pin(update: Update, context: CallbackContext) -> int:
    text = 'Please provide Pin Code'
    update.callback_query.answer()
    update.callback_query.edit_message_text(text=text)
    return PIN


def select_location(update: Update, context: CallbackContext) -> int:
    text = 'Please share current location'
    update.callback_query.answer()
    update.callback_query.edit_message_text(text=text)
    return LOCATION


def select_vaccinated(update: Update, context: CallbackContext) -> int:
    text = 'Thanks for using me !!!'
    update.callback_query.answer()
    update.callback_query.edit_message_text(text=text)
    return END


def main():
    """Start the bot."""
    # Create the Updater and pass it your bot's token.
    # Make sure to set use_context=True to use the new context based callbacks
    # Post version 12 this will no longer be necessary
    updater = Updater("")

    # Get the dispatcher to register handlers
    dp = updater.dispatcher
    # on noncommand i.e message - echo the message on Telegram
    # dp.add_handler(MessageHandler(Filters.text, echo))
    # params= VaccineHandler.Params
    
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
        SELECTING_ACTION:
                     [CallbackQueryHandler(select_pin, pattern='^' + str(PIN) + '$'),
                      CallbackQueryHandler(select_location, pattern='^' + str(LOCATION) + '$'),
                      CallbackQueryHandler(select_vaccinated, pattern='^' + str(END) + '$')],
        PIN: [MessageHandler(Filters.regex("[0-9]{6}"), pin)],
        LOCATION: [MessageHandler(Filters.location, location), CommandHandler('vaccinated', vaccinated)],
        DATE: [MessageHandler(Filters.text, date), CommandHandler('vaccinated', vaccinated)],
        # reqstates['COMPLETE']:[MessageHandler(Filters.text, complete),CommandHandler('vaccinated', params.vaccinated)]
        },
        fallbacks=[CommandHandler('cancel', cancel)],
      )

    # log all errors
    dp.add_handler(conv_handler)
    dp.add_error_handler(error)

    # Start the Bot
    updater.start_polling()

    # Run the bot until you press Ctrl-C or the process receives SIGINT,
    # SIGTERM or SIGABRT. This should be used most of the time, since
    # start_polling() is non-blocking and will stop the bot gracefully.
    updater.idle()


if __name__ == '__main__':
    main()
