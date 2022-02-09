# Copyright (C) 2005-2021 Splunk Inc. All Rights Reserved.

import sys
import json
import time

from splunk.clilib.bundle_paths import make_splunkhome_path

sys.path.append(make_splunkhome_path(['etc', 'apps', 'SA-ITOA', 'lib']))
import itsi_path

from SA_ITOA_app_common.splunklib import results
from SA_ITOA_app_common.splunklib import client
from SA_ITOA_app_common.splunklib.binding import HTTPError
from ITOA.setup_logging import getLogger
from itsi.event_management.sdk.custom_group_action_base import CustomGroupActionBase
from ITOA.event_management.notable_event_ticketing import ExternalTicket
from ITOA.event_management.notable_event_utils import ActionDispatchConfiguration
from ITOA.event_management.notable_event_utils import Audit


class SnowStreamingCommandWrapper(CustomGroupActionBase):
    """
    Class that performs ServiceNow event creation followed by External Ticket creation.
    """

    def __init__(self, settings, audit_token_name='Auto Generated ITSI Notable Index Audit Token'):
        """
        Initialize the object
        @type settings: dict/basestring
        @param settings: incoming settings for this alert action that splunkd
            passes via stdin.

        @returns Nothing
        """
        self.logger = getLogger(logger_name="itsi.event_action.snow_wrapper_event")

        super(SnowStreamingCommandWrapper, self).__init__(settings, self.logger)

        self.action_dispatch_config = ActionDispatchConfiguration(self.get_session_key(), self.logger)
        self.search_command = 'snowevent'
        self.search_ticket_id_field_name = 'Sys Id'
        self.search_ticket_url_field_name = 'Event Link'
        self.ticket_system_field_value = 'Service Now Event'
        self.service = client.connect(token=self.get_session_key(), app='SA-ITOA')
        self.audit = Audit(self.get_session_key(), audit_token_name)
        self.itsi_policy_id = self.settings.get('result', {}).get('itsi_policy_id', None)
        self.kwargs = {}

    def wait_for_job(self, searchjob, maxtime=-1):
        """
        Wait up to maxtime seconds for searchjob to finish.  If maxtime is
        negative (default), waits forever.  Returns true, if job finished.
        """
        pause = 0.2
        lapsed = 0.0
        while not searchjob.is_done():
            time.sleep(pause)
            lapsed += pause
            if maxtime >= 0 and lapsed > maxtime:
                break
        return searchjob.is_done()

    def generate_search(self):
        """
        Formats streaming search command with params passed in from alert action.
        """
        config = self.get_config()
        search_string = '| ' + self.search_command
        if config:
            ci_identifier = config.get('configuration_item', None)
            if ci_identifier:
                config['ci_identifier'] = ci_identifier
            for field_name, value in config.items():
                value = value.replace('"', '\\"')  # escape double quotes
                if field_name in ['account' , 'node', 'resource', 'type', 'severity', 'addition_info', 'url', 'description', 'custom_fields']:  # specific fields from SNOW TA event
                    search_string += ' --{field_name} "{value}"'.format(field_name=field_name, value=value)
            search_string = search_string.rstrip(',')
        return search_string

    def run_search(self, search):
        """
        Runs the search command
        """
        try:
            search_job = self.service.jobs.create(search)
        except HTTPError as e:
            raise Exception('Error when running search "{search}". Error: {e}'.format(search=search, e=e))
        return search_job

    def get_search_results(self, search_job):
        """
        Fetches the results of the streaming search command
        """
        try:
            self.wait_for_job(search_job, 600)
            result = next(results.ResultsReader(search_job.results()))
        except StopIteration:
            error_messages = search_job.messages.get('error', [])
            if len(error_messages) > 0:
                 raise Exception('Search command "{}" failed with the following error: {}'.format(self.search_command, ' '.join(error_messages)))
            else:
                raise Exception('Search command "{}" failed to return a result. Check the add-on configuration and input parameters.'.format(self.search_command))
        return result

    def create_external_ticket(self, search_results):
        """
        Creates an external ticket object with results of streaming search command
        """
        ticket_id = search_results.get(self.search_ticket_id_field_name, None)
        ticket_url = search_results.get(self.search_ticket_url_field_name, None)
        if not ticket_id or not ticket_url:
             raise Exception('Search command "{}" failed to return an incident ID or URL. Check the add-on configuration and input parameters.'.format(self.search_command))

        ticket_system = self.ticket_system_field_value
        group_id = self.get_config()['correlation_id']
        external_ticket = ExternalTicket(
                group_id, self.get_session_key(), self.logger,
                action_dispatch_config=self.action_dispatch_config,
                current_user_name=self.settings.get('owner', None)
            )
        return external_ticket.upsert(ticket_system, ticket_id, ticket_url, itsi_policy_id=self.itsi_policy_id)


    def execute(self):
        """
        Runs snow streaming command then uses the results to generate an external ticket
        """
        self.logger.debug('Received settings from splunkd=`%s`', json.dumps(self.settings))

        try:
            search = self.generate_search()
            search_job = self.run_search(search)
            search_results = self.get_search_results(search_job)
            self.create_external_ticket(search_results)
        except Exception as e:
            self.logger.error('Failed to execute create snow event action.')
            self.logger.exception(e)
            self.audit.send_activity_to_audit({
                'event_id': self.get_config()['correlation_id'],
                'itsi_policy_id': self.itsi_policy_id
            }, str(e), 'Action failed for Episode.')
            sys.exit(1)

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == '--execute':
        input_params = sys.stdin.read()
        search_command = SnowStreamingCommandWrapper(input_params)
        search_command.execute()
