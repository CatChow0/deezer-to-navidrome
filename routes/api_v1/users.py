"""The accounts of this app (Admins), and the clears of your own profiles."""
from routes import users as web
from routes.api_v1 import expose

expose("/users", web.list_route, name="users")
expose("/users/names", web.names_route, name="user_names")
expose("/users", web.create_route, ("POST",), name="user_create")
expose("/users/<user_id>", web.update_route, ("PATCH",), name="user_update")
expose("/users/<user_id>", web.delete_route, ("DELETE",), name="user_delete")
expose("/users/<user_id>/password", web.password_route, ("POST",), name="user_password")
expose("/users/<user_id>/recovery", web.recovery_route, ("POST",), name="user_recovery", cache=False)
expose("/profiles/clear/<what>", web.clear_profiles_route, ("POST",), name="profiles_clear")
