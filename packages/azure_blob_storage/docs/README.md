# Custom Azure Blob Storage Input

Use the `azure blob storage input` to read content from files stored in containers which reside on your Azure Cloud.
The input can be configured to work with and without polling, though currently, if polling is disabled it will only 
perform a one time passthrough, list the file contents and end the process. Polling is generally recommented for most cases
even though it can get expensive with dealing with a very large number of files.

*To mitigate errors and ensure a stable processing environment, this input employs the following features :* 

1.  When processing azure blob containers, if suddenly there is any outage, the process will be able to resume post the last file it processed 
    and was successfully able to save the state for. 

2.  If any errors occur for certain files, they will be logged appropriately, but the rest of the 
    files will continue to be processed normally. 

3.  If any major error occurs which stops the main thread, the logs will be appropriately generated,
    describing said error.

[id="supported-types"]
NOTE: Currently only `JSON` and `NDJSON` are supported blob/file formats. Blobs/files may be also be gzip compressed. As for authentication types, we currently have support for 
`shared access keys` and `connection strings`.

## ECS Field Mapping
This integration includes the ECS Dynamic Template, all fields that follows the ECS Schema will get assigned the correct index field mapping and does not need to be added manually.

## Ingest Pipelines
Custom ingest pipelines may be added by adding the name to the pipeline configuration option, creating custom ingest pipelines can be done either through the API or the [Ingest Node Pipeline UI](/app/management/ingest/ingest_pipelines/).
