# Splunk-ITSI-to-SNOW-Event
Splunk ITSI -> ServiceNow events

This is a Notable Event Action that triggers a ServiceNow event (OOB only supports incidents).  
## Prerequisite:

1. ServiceNow add-on installed and configured

## Instructions:
1. Extract .tgz to $SPLUNK_HOME/etc/apps/

2. Create correlation search to populate normalized fields

3. For manual event creation, select "ServiceNow Event Integration" from the actions drop-down

4. For automated event creation, create a notable event aggregation policy and configure the "ServiceNow Event Integration"
