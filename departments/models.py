# This app deliberately has no models of its own. ServiceOrder - the data
# departments actually work with - lives in the `orders` app instead,
# since both `doctors` (which creates orders) and `departments` (which
# fulfills them) need to read and write it. Putting it in either app
# would make the other depend on that app's internals.
