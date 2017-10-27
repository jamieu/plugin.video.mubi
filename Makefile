ADDON = plugin.video.mubi

SOURCE_FILES = addon.xml addon.py
SOURCE_FILES += fanart.jpg icon.png
SOURCE_FILES += README.md LICENSE.txt
SOURCE_FILES += resources/__init__.py resources/settings.xml
SOURCE_FILES += resources/language/English/strings.xml
SOURCE_FILES += resources/lib/__init__.py resources/lib/mubi.py
SOURCE_FILES += resources/lib/__init__.py resources/lib/simplecachedummy.py

PACKAGING_DIR = packaging
PACKAGE_FILE = $(PACKAGING_DIR)/$(ADDON).zip

DIST_FILES = $(addprefix $(PACKAGING_DIR)/$(ADDON)/,$(SOURCE_FILES))

all: dist

dist: $(PACKAGE_FILE)

clean:
	rm -f $(PACKAGE_FILE)
	rm -Rf $(PACKAGING_DIR)

$(PACKAGE_FILE): $(DIST_FILES)
	cd $(PACKAGING_DIR) && zip -9r $(ADDON).zip $(ADDON)
	@echo "Add-on package created at $(PACKAGE_FILE)"

$(PACKAGING_DIR)/$(ADDON)/%: ./%
	mkdir -p `dirname $@`
	cp -f $< $@

.PHONY: dist
