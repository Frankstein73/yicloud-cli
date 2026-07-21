# yicloud-cli

`yicloud-cli` is a command-line interface for interacting with the YiCloud platform.
It is developed against the [YiCloud OpenAPI](https://api.yicloud.com.cn/) and is intended
to make common YiCloud operations accessible from a terminal or automation workflow.

## Status

This project is at an early stage. The command structure and API coverage will evolve as
YiCloud OpenAPI integrations are added.

## Goals

- Provide a simple, script-friendly interface to YiCloud services.
- Support secure configuration of YiCloud credentials.
- Expose useful API operations as discoverable CLI commands.
- Return predictable output suitable for both humans and automation.

## API reference

The implementation is based on the official [YiCloud OpenAPI](https://api.yicloud.com.cn/).
Please consult the API documentation for authentication requirements, available endpoints,
request parameters, and response formats.

## Development

The repository currently contains the project documentation and initial scaffolding. Before
using the CLI against a YiCloud account, configure credentials according to the authentication
requirements documented by YiCloud.

## Contributing

Issues and pull requests are welcome. When proposing a change, please include the relevant
OpenAPI endpoint or behavior and explain how the change was tested.

## License

No license has been selected yet.
