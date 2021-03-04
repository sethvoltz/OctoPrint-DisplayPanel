$(function() {
    function MicroPanelViewModel(parameters) {
	var self = this;

	self.settings = parameters[0];

	self.currentImg = ko.observable();

	// Retrieve the current image from the API
	self.fetchImg = function () {
	    OctoPrint.plugins.display_panel.get().done(self.fromResponse);
	}

	// Handle the response from the API and set the current image
	self.fromResponse = function(data) {
	    self.currentImg(data.image_data);
	}

	// Retrieve the current image once the page loads
	self.onStartupComplete = function () {
	    self.fetchImg();
	}

	// Refresh the current image (button handler)
	self.btnRefresh = function() {
	    self.fetchImg();
	}

	// Pass the other buttons to the API and update the image
	self.btnMenu = function() {
	    OctoPrint.plugins.display_panel.press('mode')
		.done(self.fromResponse);
	}
	self.btnCancel = function() {
	    OctoPrint.plugins.display_panel.press('cancel')
		.done(self.fromResponse);
	}
	self.btnPlay = function() {
	    OctoPrint.plugins.display_panel.press('play')
		.done(self.fromResponse);
	}
	self.btnPause = function() {
	    OctoPrint.plugins.display_panel.press('pause')
		.done(self.fromResponse);
	}
    }

    OCTOPRINT_VIEWMODELS.push([
	MicroPanelViewModel,
	[],
	["#tab_plugin_display_panel"]
    ]);
});
