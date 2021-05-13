DIST_DIR=dist
TERRAFORM_DIST_NAME=domino-cdk-terraform

VERSION := $(shell python -c "from cdk.domino_cdk import __version__; print(__version__)")

.PHONY: dist

dist:
	@echo $(VERSION)
	python -m build cdk -o $(DIST_DIR)
	cd terraform && tar -zcvvf ../$(DIST_DIR)/$(TERRAFORM_DIST_NAME)-$(VERSION).tar.gz ./*

clean:
	rm -Rf $(DIST_DIR) cdk/build cdk/domino_cdk.egg-info
