from http import HTTPStatus

from celery.result import AsyncResult, GroupResult
from flask import Flask, request, abort, make_response, jsonify

from celery_app import app as celery_app
from tasks import compute_task
from services import get_calculation_input

from flask_cors import CORS
from flask_compress import Compress

from werkzeug.security import generate_password_hash, check_password_hash
from flask_httpauth import HTTPBasicAuth

import os

app = Flask(__name__)
CORS(app)
app.config['CORS_HEADERS'] = 'Content-Type'
Compress(app)

auth = HTTPBasicAuth()

CLIENT_ID = os.getenv('CLIENT_ID')
CLIENT_PASSWORD = os.getenv('CLIENT_PASSWORD')

pw_hashes = {
    CLIENT_ID: generate_password_hash(CLIENT_PASSWORD)
}


@auth.verify_password
def verify_password(client_id, password):
    if client_id in pw_hashes and \
            check_password_hash(pw_hashes.get(client_id), password):
        return client_id


@auth.error_handler
def auth_error(status):
    return make_response(
        jsonify({'error': 'Access denied.'}),
        status
    )



@app.errorhandler(404)
def not_found(message: str):
    return make_response(
        jsonify({'error': message}),
        404
    )


@app.errorhandler(400)
def bad_request(message: str):
    return make_response(
        jsonify({'error': message}),
        400
    )


@app.route("/task", methods=['POST'])
@auth.login_required
def process_noisetask():
    # Validate request
    if not request.json:
        abort(400)

    # Handle requests
    try:
        single_result = compute_task.delay(*get_calculation_input(request.json))
        response = {'taskId': single_result.id}

        # return jsonify(response), HTTPStatus.OK
        return make_response(
            jsonify(response),
            HTTPStatus.OK,
        )
    except KeyError as e:
        print("THIS IS THE ERROR %s " % e)
        print("THIS IS THE request %s " % request)

        return make_response(
            jsonify(e),
            HTTPStatus.OK,
        )


@app.route("/grouptasks/<grouptask_id>", methods=['GET'])
@auth.login_required
def get_grouptask(grouptask_id: str):
    group_result = GroupResult.restore(grouptask_id, app=celery_app)

    # Fields available
    # https://docs.celeryproject.org/en/stable/reference/celery.result.html#celery.result.ResultSet
    response = {
        'grouptaskId': group_result.id,
        'tasksCompleted': group_result.completed_count(),
        'tasksTotal': len(group_result.results),
        'grouptaskProcessed': group_result.ready(),
        'grouptaskSucceeded': group_result.successful(),
        'results': [result.get() for result in group_result.results if result.ready()]
    }

    return make_response(
        response,
        HTTPStatus.OK,
    )


@app.route("/tasks/<task_id>", methods=['GET'])
@auth.login_required
def get_task(task_id: str):
    async_result = AsyncResult(task_id, app=celery_app)

    # Fields available
    # https://docs.celeryproject.org/en/stable/reference/celery.result.html#celery.result.Result
    response = {
        'taskId': async_result.id,
        'taskState': async_result.state,
        'taskSucceeded': async_result.successful(),
        'resultReady': async_result.ready(),
    }
    if async_result.ready():
        response['result'] = async_result.get()

    return make_response(
        response,
        HTTPStatus.OK,
    )

"""
    *PENDING*
        The task is waiting for execution.
    *STARTED*
        The task has been started.
    *RETRY*
        The task is to be retried, possibly because of failure.
    *FAILURE*
        The task raised an exception, or has exceeded the retry limit.
        The :attr:`result` attribute then contains the
        exception raised by the task.
    *SUCCESS*
        The task executed successfully.  The :attr:`result` attribute
        then contains the tasks return value.
"""
@app.route("/tasks/<task_id>/status", methods=['GET'])
@auth.login_required
def is_task_ready(task_id: str):
    async_result = AsyncResult(task_id, app=celery_app)

    state = async_result.state
    if state == 'FAILURE':
        state = 'FAILURE : ' + str(async_result.get())

    response = {
        "status": state
    }

    return make_response(
        response,
        HTTPStatus.OK,
    )
