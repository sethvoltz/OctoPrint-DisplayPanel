$(function() {
    function MicroPanelViewModel(parameters) {
	var self = this;

	self.settings = parameters[0];

	self.currentImg = ko.observable();

	self.fetchImg = function () {
	    console.log("fetching...");
	    OctoPrint.plugins.display_panel.get().done(self.fromResponse);
	}

	self.fromResponse = function(data) {
	    console.log("got response!");
	    console.log(data);
	    self.currentImg(data.image_data);
	}

	self.onStartupComplete = function () {
	    console.log("On startup complete");
	    self.fetchImg();
	}
    }

    OCTOPRINT_VIEWMODELS.push([
	MicroPanelViewModel,
	[],
	["#tab_plugin_display_panel"]
    ]);
});
