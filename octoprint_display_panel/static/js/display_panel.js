$(function() {
    function MicroPanelViewModel(parameters) {
	var self = this;

	self.settings = parameters[0];

	self.currentImg = ko.observable();

	self.fetchImg = function () {
	    OctoPrint.plugins.display_panel.get().done(self.fromResponse);
	}

	self.fromResponse = function(data) {
	    self.currentImg(data.image_data);
	}

	self.onStartupComplete = function () {
	    self.fetchImg();
	}

	self.btnRefresh = function() {
	    self.fetchImg();
	}

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
