(function (global, factory) {
    if (typeof define === "function" && define.amd) {
        define(["OctoPrintClient"], factory);
    } else {
        factory(global.OctoPrintClient);
    }
})(this, function (OctoPrintClient) {
    var OctoPrintMicroPanelClient = function (base) {
        this.base = base;
    };

    OctoPrintMicroPanelClient.prototype.get = function (refresh, opts) {
        return this.base.get(this.base.getSimpleApiUrl("display_panel"), opts);
    };

    OctoPrintMicroPanelClient.prototype.press = function (label, opts) {
        var data = {
            label: label
        };
        return this.base.simpleApiCommand("display_panel", "press", data, opts);
    };

    OctoPrintClient.registerPluginComponent(
        "display_panel",
        OctoPrintMicroPanelClient
    );
    return OctoPrintMicroPanelClient;
});
